from django.core.management.base import BaseCommand

from anonymizer_app.prompt_template_store import sync_templates_to_db


class Command(BaseCommand):
    help = 'Refresh Template cache records from anonymizer_app/prompt_templates/*.txt.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--prune-stale',
            action='store_true',
            help='Delete Template cache records that no longer have a source txt file.',
        )

    def handle(self, *args, **options):
        result = sync_templates_to_db(prune_stale=options['prune_stale'])

        self.stdout.write(self.style.SUCCESS(
            'Prompt template cache refreshed. '
            f'created={result["created"]}, updated={result["updated"]}'
        ))
