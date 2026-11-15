# La notificación del aviso de faltantes pasa al modelo general del núcleo (nucleo.Notificacion).
# Orden: se agrega la referencia, se copian los datos de cada aviso y luego se quitan los campos viejos.

import django.db.models.deletion
from django.db import migrations, models


def pasar_al_nucleo(apps, schema_editor):
    Validacion = apps.get_model("recepcion", "Validacion")
    Notificacion = apps.get_model("nucleo", "Notificacion")
    Usuario = apps.get_model("nucleo", "Usuario")
    for val in Validacion.objects.filter(resultado="faltantes").select_related("expediente"):
        exp = val.expediente
        notif = Notificacion.objects.create(
            expediente=exp, tipo="faltantes", asunto="Aviso de faltantes", destinatario_id=exp.solicitante_id,
            enviada_por_id=val.usuario_id, unidad_origen_id=Usuario.objects.filter(pk=val.usuario_id).values_list("unidad_id", flat=True).first(), delegacion_id=exp.delegacion_id,
            enviada_en=val.fecha_hora, acuse_envio_id=val.acuse_id,
            notificada_en=val.notificado_en, notificada_por_id=val.notificado_por_id,
            medio="personal" if val.notificado_en else "", acuse_notificacion_id=val.acuse_notificacion_id,
            datos={"validacion": val.pk, "fecha_limite": val.fecha_limite.isoformat() if val.fecha_limite else None,
                   "migrada": True},
        )
        val.notificacion_id = notif.pk
        val.save(update_fields=["notificacion"])


def regresar(apps, schema_editor):
    Validacion = apps.get_model("recepcion", "Validacion")
    for val in Validacion.objects.filter(notificacion__isnull=False).select_related("notificacion"):
        n = val.notificacion
        val.notificado_en = n.notificada_en
        val.notificado_por_id = n.notificada_por_id
        val.acuse_notificacion_id = n.acuse_notificacion_id
        val.save(update_fields=["notificado_en", "notificado_por", "acuse_notificacion"])


class Migration(migrations.Migration):

    dependencies = [
        ('nucleo', '0004_notificaciones'),
        ('recepcion', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalvalidacion',
            name='notificacion',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text='Aviso de faltantes: su notificación por conducto de la Delegación (núcleo).', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='nucleo.notificacion'),
        ),
        migrations.AddField(
            model_name='validacion',
            name='notificacion',
            field=models.OneToOneField(blank=True, help_text='Aviso de faltantes: su notificación por conducto de la Delegación (núcleo).', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='validacion', to='nucleo.notificacion'),
        ),
        migrations.RunPython(pasar_al_nucleo, regresar),
        migrations.RemoveField(
            model_name='historicalvalidacion',
            name='acuse_notificacion',
        ),
        migrations.RemoveField(
            model_name='historicalvalidacion',
            name='notificado_en',
        ),
        migrations.RemoveField(
            model_name='historicalvalidacion',
            name='notificado_por',
        ),
        migrations.RemoveField(
            model_name='validacion',
            name='acuse_notificacion',
        ),
        migrations.RemoveField(
            model_name='validacion',
            name='notificado_en',
        ),
        migrations.RemoveField(
            model_name='validacion',
            name='notificado_por',
        ),
    ]
