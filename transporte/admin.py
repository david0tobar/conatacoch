from django.contrib import admin
from .models import Jornada, Perfil, Recorrido, Valoracion, Vehiculo


@admin.register(Vehiculo)
class VehiculoAdmin(admin.ModelAdmin):
    list_display = ("patente", "modelo", "capacidad", "recorrido", "lista_conductores", "aprobado")
    list_filter = ("aprobado", "recorrido")
    filter_horizontal = ("conductores",)
    actions = ["aprobar"]

    @admin.display(description="Conductores")
    def lista_conductores(self, obj):
        return ", ".join(u.get_full_name() or u.username for u in obj.conductores.all()) or "-"

    @admin.action(description="Aprobar vehículos seleccionados")
    def aprobar(self, request, queryset):
        queryset.update(aprobado=True)


@admin.register(Valoracion)
class ValoracionAdmin(admin.ModelAdmin):
    list_display = ("jornada", "puntaje", "categoria", "revisada", "creada")
    list_filter = ("categoria", "revisada")


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("usuario", "rut", "rol")
    list_filter = ("rol",)
    search_fields = ("rut", "usuario__first_name")


@admin.register(Recorrido)
class RecorridoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tarifa", "activo")
    list_filter = ("activo",)


@admin.register(Jornada)
class JornadaAdmin(admin.ModelAdmin):
    list_display = ("conductor", "vehiculo", "inicio", "fin")
    list_filter = ("fin",)
    actions = ["cerrar"]

    @admin.action(description="Cerrar jornadas seleccionadas")
    def cerrar(self, request, queryset):
        from django.utils import timezone
        queryset.filter(fin__isnull=True).update(fin=timezone.now(), lat=None, lng=None)
