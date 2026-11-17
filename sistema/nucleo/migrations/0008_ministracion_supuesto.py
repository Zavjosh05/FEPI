from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0007_tipo_notificacion_pago'),
    ]

    operations = [
        migrations.AddField(
            model_name='ministracion',
            name='supuesto',
            field=models.BooleanField(default=False, help_text='El porcentaje no está en las ROP: es un supuesto del archivo de reglas por confirmar (PEG).'),
        ),
    ]
