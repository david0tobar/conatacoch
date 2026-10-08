from django.contrib.auth import views as auth_views
from django.urls import path
from . import panel, views
from .forms import LoginForm

urlpatterns = [
    path("", views.mapa, name="mapa"),
    path("registro/", views.registro, name="registro"),
    path("login/", auth_views.LoginView.as_view(authentication_form=LoginForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("cambiar-clave/", panel.cambiar_clave, name="cambiar_clave"),
    path("panel/", panel.panel_inicio, name="panel"),
    path("panel/personas/", panel.personas, name="panel_personas"),
    path("panel/personas/nueva/", panel.persona_nueva, name="panel_persona_nueva"),
    path("panel/personas/<int:pk>/", panel.persona_editar, name="panel_persona_editar"),
    path("panel/personas/<int:pk>/clave/", panel.persona_clave, name="panel_persona_clave"),
    path("panel/personas/<int:pk>/estado/", panel.persona_estado, name="panel_persona_estado"),
    path("panel/vehiculos/", panel.vehiculos, name="panel_vehiculos"),
    path("panel/vehiculos/nuevo/", panel.vehiculo_form, name="panel_vehiculo_nuevo"),
    path("panel/vehiculos/<int:pk>/", panel.vehiculo_form, name="panel_vehiculo_editar"),
    path("panel/vehiculos/<int:pk>/aprobar/", panel.vehiculo_aprobar, name="panel_vehiculo_aprobar"),
    path("panel/vehiculos/<int:pk>/conductor/", panel.vehiculo_conductor, name="panel_vehiculo_conductor"),
    path("conductor/", views.panel_conductor, name="conductor"),
    path("gestion/recorridos/", views.gestion_recorridos, name="gestion_recorridos"),
    path("conductor/foto/", views.subir_foto, name="subir_foto"),
    path("api/recorridos/guardar/", views.api_guardar_recorrido, name="api_guardar_recorrido"),
    path("api/recorridos/eliminar/", views.api_eliminar_recorrido, name="api_eliminar_recorrido"),
    path("api/recorridos/", views.api_recorridos, name="api_recorridos"),
    path("api/colectivos/", views.api_colectivos, name="api_colectivos"),
    path("api/jornada/iniciar/", views.api_iniciar, name="api_iniciar"),
    path("api/jornada/actualizar/", views.api_actualizar, name="api_actualizar"),
    path("api/jornada/finalizar/", views.api_finalizar, name="api_finalizar"),
    path("api/valorar/", views.api_valorar, name="api_valorar"),
]
