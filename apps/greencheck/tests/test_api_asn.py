import logging
import pytest

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from .. import models as gc_models
from .. import viewsets as gc_viewsets
from ...accounts import models as ac_models

User = get_user_model()

pytestmark = pytest.mark.django_db

logger = logging.getLogger(__name__)

rf = APIRequestFactory()


@pytest.fixture
def another_host_user():
    u = User(username="another_user", email="another@example.com")
    u.set_password("topSekrit")
    return u


class TestASNViewSetList:
    def test_get_asn_empty(
        self, hosting_provider_with_sample_user: ac_models.Hostingprovider
    ):
        """
        Exercise the simplest happy path - we return an empty list for a hosting
        provider with no ASNS registered.
        """

        rf = APIRequestFactory()
        url_path = reverse("asn-list")
        request = rf.get(url_path)
        request.user = hosting_provider_with_sample_user.user_set.first()

        # GET end point for IP Ranges
        view = gc_viewsets.ASNViewSet.as_view({"get": "list"})

        response = view(request)

        # check contents
        assert response.status_code == 200
        assert len(response.data) == 0

    def test_get_asn_list(
        self,
        hosting_provider_with_sample_user: ac_models.Hostingprovider,
        green_asn: gc_models.GreencheckASN,
    ):
        """
        Check that we can list the ASNs for given provider
        """
        green_asn.save()

        rf = APIRequestFactory()
        url_path = reverse("asn-list")
        request = rf.get(url_path)
        request.user = hosting_provider_with_sample_user.user_set.first()

        # GET end point for IP Ranges
        view = gc_viewsets.ASNViewSet.as_view({"get": "list"})

        response = view(request)

        # check contents
        assert response.status_code == 200
        assert len(response.data) == 1

        first_asn_data = response.data[0]
        assert first_asn_data["id"] == green_asn.id
        assert first_asn_data["asn"] == green_asn.asn

    def test_get_asn_retrieve(
        self,
        hosting_provider_with_sample_user: ac_models.Hostingprovider,
        green_asn: gc_models.GreencheckASN,
    ):
        """
        Check that we can fetch an individual ASN for the provider
        """
        green_asn.save()

        rf = APIRequestFactory()
        url_path = reverse("asn-detail", kwargs={"pk": green_asn.id})
        request = rf.get(url_path)
        request.user = hosting_provider_with_sample_user.user_set.first()

        # GET end point for IP Ranges
        view = gc_viewsets.ASNViewSet.as_view({"get": "retrieve"})

        response = view(request, pk=green_asn.id)

        # check contents
        assert response.status_code == 200

        response.data["asn"] == green_asn.asn
        response.data["id"] == green_asn.id
        response.data["hostingprovider"] == green_asn.hostingprovider.id

    def test_get_asn_create(
        self, hosting_provider_with_sample_user: ac_models.Hostingprovider,
    ):
        """
        Can we create an new ASN over the API, for our hosting provider?
        """
        rf = APIRequestFactory()
        url_path = reverse("asn-list")
        user = hosting_provider_with_sample_user.user_set.first()
        data = {
            "asn": 12345,
            "hostingprovider": hosting_provider_with_sample_user.id,
        }
        request = rf.post(url_path, data)
        request.user = user

        # GET end point for IP Ranges
        view = gc_viewsets.ASNViewSet.as_view({"post": "create"})

        response = view(request)

        # check contents
        assert response.status_code == 201
        response.data["asn"] == 12345
        response.data["hostingprovider"] == hosting_provider_with_sample_user.id

        green_asn, *_ = gc_models.GreencheckASN.objects.filter(asn=12345)
        response.data["id"] == green_asn.id

    def test_get_asn_delete(
        self,
        hosting_provider_with_sample_user: ac_models.Hostingprovider,
        green_asn: gc_models.GreencheckASN,
    ):
        """
        Can we delete an ASN via the API, marking it as 'inactive' in our database?
        """

        green_asn.save()

        rf = APIRequestFactory()
        url_path = reverse("asn-detail", kwargs={"pk": green_asn.id})
        user = hosting_provider_with_sample_user.user_set.first()
        request = rf.delete(url_path)
        request.user = user

        # GET end point for IP Ranges
        view = gc_viewsets.ASNViewSet.as_view({"delete": "destroy"})

        response = view(request, pk=green_asn.id)

        # check contents
        assert response.status_code == 204
        assert gc_models.GreencheckASN.objects.filter(asn=12345).count() == 1

        fetched_green_asn = gc_models.GreencheckASN.objects.filter(asn=12345).first()
        assert not fetched_green_asn.active

    def test_can_only_create_asns_for_own_hosting_provider(
        self,
        hosting_provider_with_sample_user: ac_models.Hostingprovider,
        another_host_user: User,
    ):
        """
        An user must be associated with a hosting provider to be able to create
        ASNs or IP Ranges for the provider
        """

        rf = APIRequestFactory()
        url_path = reverse("asn-list")
        request = rf.delete(url_path)
        request.user = another_host_user

        # GET end point for IP Ranges
        view = gc_viewsets.ASNViewSet.as_view({"post": "create"})

        response = view(request)

        # check contents
        assert response.status_code == 405
        assert gc_models.GreencheckASN.objects.filter(asn=12345).count() == 0

    def test_can_only_destroy_asns_for_own_hosting_provider(
        self,
        hosting_provider_with_sample_user: ac_models.Hostingprovider,
        another_host_user: User,
        green_asn: gc_models.GreencheckASN,
    ):
        """
        An user must be associated with a hosting provider to be able
         to create or destroy ASNs or IP Ranges for the provider
        """
        green_asn.save()
        assert gc_models.GreencheckASN.objects.filter(asn=12345).count() == 1

        rf = APIRequestFactory()
        url_path = reverse("asn-detail", kwargs={"pk": green_asn.id})
        hosting_provider_with_sample_user.user_set.first()
        request = rf.delete(url_path)
        request.user = another_host_user

        # GET end point for IP Ranges
        view = gc_viewsets.ASNViewSet.as_view({"delete": "destroy"})

        response = view(request, pk=green_asn.id)

        # check contents
        assert response.status_code == 404
        assert (
            gc_models.GreencheckASN.objects.filter(asn=12345, active=True).count() == 1
        )

