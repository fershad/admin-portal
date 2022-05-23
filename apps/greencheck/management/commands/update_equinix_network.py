from apps.greencheck.importers.equinix_importer import EquinixImporter
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, *args, **options):
        importer = EquinixImporter()
        data = importer.fetch_data_from_source()
        importer.process_addresses(data)

        # TODO: Implement output