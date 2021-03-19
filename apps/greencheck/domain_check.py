"""
A python implementation of the domain checker powering the previous php based versions
of the Greencheck API.

This follows largely the same approach:

1. take a domain or ip address
2. convert to ip address if need be.
3. check for existing match in the ip ranges, choosing the smallest range
   that matches the query
4. if no match, look up ASN from provided ip address
5. check against registered ASNs
6. if no matches left, report grey
"""
import socket
import logging
from .models import GreenDomain

from . import legacy_workers
from ipwhois.asn import IPASN
from ipwhois.net import Net
from ipwhois.exceptions import IPDefinedError
import ipaddress
from django.utils import timezone
import urllib
import tld

logger = logging.getLogger(__name__)


class GreenDomainChecker:
    """
    The checking class. Used to run a check against a domain, to find the
    matching SiteCheck result, that we might log.
    """

    def validate_domain(self, url) -> str:
        """
        Attempt to clean the provided url, and pull
        return the domain, or ip address
        """

        is_valid_tld = tld.is_tld(url)

        # looks like a domain
        if is_valid_tld:
            res = tld.get_tld(url, fix_protocol=True, as_object=True)
            return res.parsed_url.netloc

        # not a domain, try ip address:
        if not is_valid_tld:
            parsed_url = urllib.parse.urlparse(url)
            if not parsed_url.netloc:
                # add the //, so that our url reading code
                # parses it properly
                parsed_url = urllib.parse.urlparse(f"//{url}")
            return parsed_url.netloc

    def perform_full_lookup(self, domain) -> GreenDomain:
        """
        Return a Green Domain object from doing a lookup.
        """
        res = self.check_domain(domain)

        if not res.green:
            return GreenDomain.grey_result(domain=res.url)

        # return a domain result, but don't save it,
        # as persisting it is handled asynchronously
        # by another worker, and logged to both the greencheck
        # table and this 'cache' table
        return GreenDomain.from_sitecheck(res)

    def asn_from_ip(self, ip_address):
        """
        Check the IP against the IP 2 ASN service provided by the
        Team Cymru IP to ASN Mapping Service
        https://ipwhois.readthedocs.io/en/latest/ASN.html#asn-origin-lookups
        """
        network = Net(ip_address)
        obj = IPASN(network)
        res = obj.lookup()
        return res["asn"]

    def convert_domain_to_ip(
        self, domain
    ) -> ipaddress.IPv4Network or ipaddress.IPv6Network:
        """
        Accepts a domain name or IP address, and returns an IPV4 or IPV6
        address
        """
        ip_string = socket.gethostbyname(domain)
        return ipaddress.ip_address(ip_string)

    def green_sitecheck_by_ip_range(self, domain, ip_address, ip_match):
        """
        Return a SiteCheck object, that has been marked as green by
        looking up against an IP range
        """
        return legacy_workers.SiteCheck(
            url=domain,
            ip=str(ip_address),
            data=True,
            green=True,
            hosting_provider_id=ip_match.hostingprovider.id,
            match_type="ip",
            match_ip_range=ip_match.id,
            cached=False,
            checked_at=timezone.now(),
        )

    def green_sitecheck_by_asn(self, domain, ip_address, matching_asn):
        return legacy_workers.SiteCheck(
            url=domain,
            ip=str(ip_address),
            data=True,
            green=True,
            hosting_provider_id=matching_asn.hostingprovider.id,
            match_type="as",
            match_ip_range=matching_asn.id,
            cached=False,
            checked_at=timezone.now(),
        )

    def grey_sitecheck(
        self, domain, ip_address,
    ):
        return legacy_workers.SiteCheck(
            url=domain,
            ip=str(ip_address),
            data=False,
            green=False,
            hosting_provider_id=None,
            match_type=None,
            match_ip_range=None,
            cached=False,
            checked_at=timezone.now(),
        )

    def check_domain(self, domain: str) -> legacy_workers.SiteCheck:
        """
        Accept a domain name and return the either a GreenDomain Object,
        or the best matching IP range forip address it resolves to.
        """

        ip_address = self.convert_domain_to_ip(domain)

        if ip_match := self.check_for_matching_ip_ranges(ip_address):
            return self.green_sitecheck_by_ip_range(domain, ip_address, ip_match)

        if matching_asn := self.check_for_matching_asn(ip_address):
            return self.green_sitecheck_by_asn(domain, ip_address, matching_asn)

        # otherwise, return a 'grey' result
        return self.grey_sitecheck(domain, ip_address)

    def check_for_matching_ip_ranges(self, ip_address):
        """
        Look up the IP ranges that include this IP address, and return
        a list of IP ranges, ordered by smallest, most precise range first.
        """
        from .models import GreencheckIp

        ip_matches = GreencheckIp.objects.filter(
            ip_end__gte=ip_address, ip_start__lte=ip_address,
        )
        # order matches by ascending range size
        return ip_matches.first()

    def check_for_matching_asn(self, ip_address):
        """
        Return the Green ASN that this IP address 'belongs' to.
        """
        from .models import GreencheckASN

        try:
            asn_result = self.asn_from_ip(ip_address)
        except IPDefinedError:
            return False
        except Exception as err:
            logger.exception(err)
            return False

        if isinstance(asn_result, int):
            return GreencheckASN.objects.filter(asn=asn_result).first()

        # we have a string containing more than one ASN.
        # look them up, and return the first green one
        asns = asn_result.split(" ")
        for asn in asns:
            asn_match = GreencheckASN.objects.filter(asn=asn)
            if asn_match:
                # we have a match, return the result
                return asn_match.first()

    def grey_urls_only(self, urls_list, queryset) -> list:
        """
        Accept a list of domain names, and a queryset of checked green
        domain objects, and return a list of only the grey domains.
        """
        green_list = [domain_object.url for domain_object in queryset]

        return [url for url in urls_list if url not in green_list]

    def build_green_greylist(self, grey_list: list, green_list) -> list:
        """
        Create a list of green and grey domains, to serialise and deliver.
        """
        grey_domains = []

        for domain in grey_list:
            gp = GreenDomain.grey_result(domain=domain)
            grey_domains.append(gp)

        evaluated_green_queryset = green_list[::1]

        return evaluated_green_queryset + grey_domains
