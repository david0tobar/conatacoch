import os
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from .rut import formatear


def ruta_foto(instance, filename):
    return f"conductores/{instance.usuario_id}_{uuid.uuid4().hex[:8]}{os.path.splitext(filename)[1].lower()}"


class Recorrido(models.Model):
    nombre = models.CharField(max_length=120)
    geometria = models.JSONField(default=list, help_text="Lista de puntos [[lat, lng], ...] sobre las calles")
    tarifa = models.PositiveIntegerField(default=0)
    tarifa_actualizada = models.DateField(null=True, blank=True)
    representante = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name="recorridos")
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


class Perfil(models.Model):
    class Rol(models.TextChoices):
        PASAJERO = "pasajero", "Pasajero"
        CONDUCTOR = "conductor", "Conductor"
        REPRESENTANTE = "representante", "Representante legal"
        ADMIN = "admin", "Administrador"

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    rol = models.CharField(max_length=15, choices=Rol.choices, default=Rol.PASAJERO)
    rut = models.CharField(max_length=12, unique=True, null=True, blank=True, help_text="Formato 12345678-5")
    foto = models.ImageField(upload_to=ruta_foto, blank=True, help_text="Foto para que los pasajeros identifiquen al conductor")
    representante = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="conductores_a_cargo", limit_choices_to={"perfil__rol": "representante"},
                                      help_text="Representante legal responsable de este conductor")
    debe_cambiar_clave = models.BooleanField(default=False, help_text="Se le exigirá cambiar la contraseña al ingresar")

    @property
    def rut_fmt(self):
        return formatear(self.rut) if self.rut else "-"

    def __str__(self):
        return f"{self.usuario.get_full_name() or self.usuario} - {self.rol}"


class Vehiculo(models.Model):
    patente = models.CharField(max_length=10, unique=True)
    modelo = models.CharField(max_length=60)
    capacidad = models.PositiveSmallIntegerField(default=4)
    recorrido = models.ForeignKey(Recorrido, on_delete=models.PROTECT, related_name="vehiculos")
    aprobado = models.BooleanField(default=False, help_text="Lo revisa el representante antes de ser público")
    conductores = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="vehiculos_asignados",
                                         limit_choices_to={"perfil__rol": "conductor"},
                                         help_text="Conductores autorizados a manejar este vehículo")

    def __str__(self):
        return self.patente


class Jornada(models.Model):
    """Un colectivo solo es visible mientras tiene una jornada abierta (fin vacío)."""
    conductor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jornadas")
    vehiculo = models.ForeignKey(Vehiculo, on_delete=models.CASCADE, related_name="jornadas")
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    asientos_libres = models.PositiveSmallIntegerField(default=0)  # dato interno: al público solo se le dice si hay o no
    actualizado = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conductor"], condition=Q(fin__isnull=True),
                                               name="una_jornada_abierta_por_conductor"),
            models.UniqueConstraint(fields=["vehiculo"], condition=Q(fin__isnull=True),
                                    name="una_jornada_abierta_por_vehiculo"),
        ]


class Valoracion(models.Model):
    class Categoria(models.TextChoices):
        FELICITACION = "felicitacion", "Felicitación"
        SUGERENCIA = "sugerencia", "Sugerencia"
        RECLAMO = "reclamo", "Reclamo"

    jornada = models.ForeignKey(Jornada, on_delete=models.CASCADE, related_name="valoraciones")
    pasajero = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    puntaje = models.PositiveSmallIntegerField()  # 1 a 5
    categoria = models.CharField(max_length=15, choices=Categoria.choices)
    comentario = models.TextField(max_length=500, blank=True)
    revisada = models.BooleanField(default=False)  # un humano revisa; no hay sanciones automáticas
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("jornada", "pasajero")
