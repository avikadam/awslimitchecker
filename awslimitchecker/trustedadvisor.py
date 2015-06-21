"""
awslimitchecker/trustedadvisor.py

The latest version of this package is available at:
<https://github.com/jantman/awslimitchecker>

################################################################################
Copyright 2015 Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>

    This file is part of awslimitchecker, also known as awslimitchecker.

    awslimitchecker is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    awslimitchecker is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with awslimitchecker.  If not, see <http://www.gnu.org/licenses/>.

The Copyright and Authors attributions contained herein may not be removed or
otherwise altered, except to add the Author attribution of a contributor to
this work. (Additional Terms pursuant to Section 7b of the AGPL v3)
################################################################################
While not legally required, I sincerely request that anyone who finds
bugs please submit them at <https://github.com/jantman/awslimitchecker> or
to me via email, and that you send any contributions or improvements
either as a pull request on GitHub, or to me via email.
################################################################################

AUTHORS:
Jason Antman <jason@jasonantman.com> <http://www.jasonantman.com>
################################################################################
"""

import boto
from dateutil import parser
import logging
logger = logging.getLogger(__name__)


class TrustedAdvisor(object):

    def __init__(self):
        """
        Class to contain all TrustedAdvisor-related logic.
        """
        self.conn = None

    def connect(self):
        if self.conn is None:
            logger.debug("Connecting to Support API (TrustedAdvisor)")
            self.conn = boto.connect_support()
            logger.info("Connected to Support API")

    def update_limits(self, services):
        """
        Poll 'Service Limits' check results from Trusted Advisor, if possible.
        Iterate over all :py:class:`~.AwsLimit` objects for the given services
        and update their limits from TA if present in TA checks.

        :param services: dict of service name (string) to
          :py:class:`~._AwsService` objects
        :type services: dict
        """
        self.connect()
        ta_results = self._poll()
        self._update_services(ta_results, services)

    def _poll(self):
        """
        Poll Trusted Advisor (Support) API for limit checks.

        Return a dict of service name (string) keys to nested dict vals, where
        each key is a limit name and each value the current numeric limit.

        e.g.:

        {
            'EC2': {
                'SomeLimit': 10,
            }
        }
        """
        logger.info("Beginning TrustedAdvisor poll")
        tmp = self._get_limit_check_id()
        if tmp is None:
            logger.critical("Unable to find 'Service Limits' Trusted Advisor "
                            "check; not using Trusted Advisor data.")
            return
        check_id, metadata = tmp
        region = self.conn.region.name
        checks = self.conn.describe_trusted_advisor_check_result(check_id)
        check_datetime = parser.parse(checks['result']['timestamp'])
        logger.debug("Got TrustedAdvisor data for check %s as of %s",
                     check_id, check_datetime)
        res = {}
        for check in checks['result']['flaggedResources']:
            if check['region'] != region:
                continue
            data = dict(zip(metadata, check['metadata']))
            if data['Service'] not in res:
                res[data['Service']] = {}
            res[data['Service']][data['Limit Name']] = int(data['Limit Amount'])
        logger.info("Finished TrustedAdvisor poll")
        return res

    def _get_limit_check_id(self):
        """
        Query currently-available TA checks, return the check ID and metadata
        of the 'performance/Service Limits' check.

        :returns: 2-tuple of Service Limits TA check ID (string),
          metadata (list)
        :rtype: tuple
        """
        logger.debug("Querying Trusted Advisor checks")
        checks = self.conn.describe_trusted_advisor_checks('en')['checks']
        for check in checks:
            if (
                    check['category'] == 'performance' and
                    check['name'] == 'Service Limits'
            ):
                logger.debug("Found TA check; id=%s", check['id'])
                return (
                    check['id'],
                    check['metadata']
                )
        logger.debug("Unable to find check with category 'performance' and "
                     "name 'Service Limits'.")
        return None

    def _update_services(self, ta_results, services):
        """
        Given a dict of TrustedAdvisor check results from :py:meth:`~._poll`
        and a dict of Service objects passed in to :py:meth:`~.update_limits`,
        updated the TrustedAdvisor limits for all services.

        :param ta_results: results returned by :py:meth:`~._poll`
        :type ta_results: dict
        :param services: dict of service names to _AwsService objects
        :type services: dict
        """
        logger.debug("Updating TA limits on all services")
        for svc_name in sorted(ta_results.keys()):
            limits = ta_results[svc_name]
            if svc_name not in services:
                logger.critical("TrustedAdvisor returned check results for "
                                "unknown service '%s'", svc_name)
                continue
            service = services[svc_name]
            for lim_name in sorted(limits.keys()):
                try:
                    service._set_ta_limit(lim_name, limits[lim_name])
                except ValueError:
                    logger.warning("TrustedAdvisor returned check results for "
                                   "unknown limit '%s' (service %s)",
                                   lim_name,
                                   svc_name)
        logger.info("Done updating TA limits on all services")
