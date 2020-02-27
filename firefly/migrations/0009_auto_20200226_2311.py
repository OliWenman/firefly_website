# Generated by Django 3.0.3 on 2020-02-26 23:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('firefly', '0008_auto_20200226_1921'),
    ]

    operations = [
        migrations.DeleteModel(
            name='FireflyTracker',
        ),
        migrations.AddField(
            model_name='fireflyresults',
            name='output_file',
            field=models.FileField(blank=True, upload_to=''),
        ),
        migrations.AddField(
            model_name='fireflyresults',
            name='status',
            field=models.CharField(default='preprocessing', max_length=14),
        ),
    ]
