# Generated by Django 2.2.13 on 2020-06-04 10:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('greencheck', '0004_auto_20200603_1109'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='greencheckipapprove',
            index=models.Index(fields=['-created'], name='greencheck__created_23c8a1_idx'),
        ),
    ]
