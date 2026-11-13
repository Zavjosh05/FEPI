from django.db import migrations, models


class Migration(migrations.Migration):
    """Ajuste a M1: requisitos que son condiciones y no documentos (no exigen archivo)."""

    dependencies = [("nucleo", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="requisito",
            name="requiere_documento",
            field=models.BooleanField(
                default=True,
                help_text="No: es una condición que se revisa (por ejemplo, la nacionalidad), no un documento que se digitaliza.",
            ),
        ),
    ]
