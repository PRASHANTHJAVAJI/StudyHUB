from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_fix_subjecttag_unique_studynote_fks'),
    ]

    operations = [
        migrations.AddField(
            model_name='studysession',
            name='category',
            field=models.CharField(
                choices=[
                    ('general', 'General'),
                    ('study_session', 'Study Session'),
                    ('conference', 'Conference'),
                ],
                default='general',
                max_length=20,
            ),
        ),
    ]
