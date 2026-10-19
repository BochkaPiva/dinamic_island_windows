"""Repair local prototypes; the old table/index collision could never install on PG."""
from django.db import migrations, models


def repair(apps, schema_editor):
    model = apps.get_model('community', 'Membership')
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(cursor, model._meta.db_table)
    if schema_editor.connection.vendor == 'sqlite' and 'community_membership' in constraints:
        # SQLite remakes the table from the migration model, including the corrected name.
        schema_editor.remove_constraint(model, models.UniqueConstraint(
            fields=['link', 'channel_id'], name='community_membership'))


class Migration(migrations.Migration):
    dependencies = [('community', '0003_communitymember_memberdevice_devicepairing_and_more')]
    operations = [migrations.RunPython(repair, migrations.RunPython.noop)]
