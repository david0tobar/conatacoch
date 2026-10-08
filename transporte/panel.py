"""Panel de administración visual: Personas y Vehículos.

Permisos:
- Administrador (o superusuario): ve y gestiona todo.
- Representante legal: solo sus recorridos, los vehículos de esos recorridos y los conductores a su cargo.
"""
import secrets
from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import PersonaForm, VehiculoForm
from .models import Jornada, Perfil, Recorrido, Vehiculo
from .rut import formatear

ADMIN, REPR, COND = Perfil.Rol.ADMIN, Perfil.Rol.REPRESENTANTE, Perfil.Rol.CONDUCTOR
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"  # sin caracteres que se confunden


def rol_de(user):
    if user.is_superuser:
        return ADMIN
    return getattr(getattr(user, "perfil", None), "rol", "")


def gestor_requerido(view):
    @wraps(view)
    def inner(request, *a, **kw):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if rol_de(request.user) not in (ADMIN, REPR):
            return redirect("mapa")
        return view(request, *a, **kw)
    return inner


def vehiculos_visibles(user):
    qs = Vehiculo.objects.select_related("recorrido").prefetch_related("conductores")
    return qs if rol_de(user) == ADMIN else qs.filter(recorrido__representante=user)


def perfiles_visibles(user):
    qs = Perfil.objects.select_related("usuario", "representante")
    return qs if rol_de(user) == ADMIN else qs.filter(rol=COND, representante=user)


def recorridos_visibles(user):
    qs = Recorrido.objects.filter(activo=True)
    return qs if rol_de(user) == ADMIN else qs.filter(representante=user)


def _ctx(request, seccion, **extra):
    return {"seccion": seccion, "es_admin": rol_de(request.user) == ADMIN, **extra}


def _cerrar_jornadas(user):
    Jornada.objects.filter(conductor=user, fin__isnull=True).update(fin=timezone.now(), lat=None, lng=None)


# ====================== contraseña ======================
@login_required
def cambiar_clave(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        Perfil.objects.filter(usuario=user).update(debe_cambiar_clave=False)
        messages.success(request, "Tu contraseña se actualizó.")
        return redirect("mapa")
    obligatorio = getattr(getattr(request.user, "perfil", None), "debe_cambiar_clave", False)
    return render(request, "registration/cambiar_clave.html", {"form": form, "obligatorio": obligatorio})


# ====================== personas ======================
@gestor_requerido
def panel_inicio(request):
    return redirect("panel_personas")


@gestor_requerido
def personas(request):
    qs = perfiles_visibles(request.user).prefetch_related("usuario__vehiculos_asignados")
    q = request.GET.get("q", "").strip()
    rol = request.GET.get("rol", "")
    if q:
        qs = qs.filter(Q(usuario__first_name__icontains=q) | Q(rut__icontains=q.replace(".", "").replace(" ", "")))
    if rol in Perfil.Rol.values:
        qs = qs.filter(rol=rol)
    clave = request.session.pop("clave_nueva", None)  # se muestra una sola vez
    return render(request, "panel/personas.html", _ctx(
        request, "personas", perfiles=qs.order_by("usuario__first_name"), q=q, rol=rol,
        roles=Perfil.Rol.choices, clave_nueva=clave))


def _kw_form(actor, crear, bloquear_rol=False):
    return dict(es_admin=rol_de(actor) == ADMIN, crear=crear, bloquear_rol=bloquear_rol,
                vehiculos_qs=vehiculos_visibles(actor), recorridos_qs=Recorrido.objects.filter(activo=True))


def _aplicar(actor, perfil, d):
    """Guarda foto, rol, representante, vehículos y recorridos respetando el alcance de quien edita."""
    user, es_admin = perfil.usuario, rol_de(actor) == ADMIN
    user.first_name = d["nombre"]
    user.save()
    if d.get("foto"):
        if perfil.foto:
            perfil.foto.delete(save=False)
        perfil.foto = d["foto"]
    perfil.rol = d["rol"]

    if perfil.rol == COND:
        perfil.representante = d.get("representante") if es_admin else actor
        elegidos = set(d.get("vehiculos") or [])
        for v in vehiculos_visibles(actor):          # solo toca los vehículos que el actor puede gestionar
            (v.conductores.add if v in elegidos else v.conductores.remove)(user)
    else:
        perfil.representante = None
        for v in Vehiculo.objects.filter(conductores=user):
            v.conductores.remove(user)
        _cerrar_jornadas(user)

    if es_admin:
        if perfil.rol == REPR:
            ids = [r.pk for r in (d.get("recorridos") or [])]
            Recorrido.objects.filter(representante=user).exclude(pk__in=ids).update(representante=None)
            Recorrido.objects.filter(pk__in=ids).update(representante=user)
        else:
            Recorrido.objects.filter(representante=user).update(representante=None)
            Perfil.objects.filter(representante=user).update(representante=None)
    perfil.save()


@gestor_requerido
def persona_nueva(request):
    form = PersonaForm(request.POST or None, request.FILES or None, **_kw_form(request.user, crear=True))
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        clave = "".join(secrets.choice(ALFABETO) for _ in range(10))
        with transaction.atomic():
            user = User.objects.create_user(username=d["rut"], password=clave)
            perfil = Perfil.objects.create(usuario=user, rol=d["rol"], rut=d["rut"], debe_cambiar_clave=True)
            _aplicar(request.user, perfil, d)
        request.session["clave_nueva"] = [d["nombre"], formatear(d["rut"]), clave]
        messages.success(request, f"Se creó la cuenta de {d['nombre']}.")
        return redirect("panel_personas")
    return render(request, "panel/persona_form.html", _ctx(request, "personas", form=form, perfil=None))


@gestor_requerido
def persona_editar(request, pk):
    perfil = get_object_or_404(perfiles_visibles(request.user), pk=pk)
    user = perfil.usuario
    bloquear = user.pk == request.user.pk or user.is_superuser   # nadie se quita su propio rol
    inicial = {"nombre": user.first_name, "rol": perfil.rol, "representante": perfil.representante_id,
               "vehiculos": vehiculos_visibles(request.user).filter(conductores=user),
               "recorridos": Recorrido.objects.filter(representante=user)}
    form = PersonaForm(request.POST or None, request.FILES or None, initial=inicial,
                       **_kw_form(request.user, crear=False, bloquear_rol=bloquear))
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            _aplicar(request.user, perfil, form.cleaned_data)
        messages.success(request, "Los cambios se guardaron.")
        return redirect("panel_personas")
    return render(request, "panel/persona_form.html", _ctx(request, "personas", form=form, perfil=perfil, bloquear=bloquear))


def _objetivo(request, pk):
    """Perfil sobre el que se puede actuar (restablecer clave / desactivar), o None si no corresponde."""
    perfil = get_object_or_404(perfiles_visibles(request.user), pk=pk)
    if perfil.usuario.pk == request.user.pk or perfil.usuario.is_superuser:
        messages.error(request, "No puedes realizar esta acción sobre esa cuenta.")
        return None
    return perfil


@require_POST
@gestor_requerido
def persona_clave(request, pk):
    perfil = _objetivo(request, pk)
    if perfil:
        clave = "".join(secrets.choice(ALFABETO) for _ in range(10))
        perfil.usuario.set_password(clave)   # además cierra sus sesiones abiertas
        perfil.usuario.save()
        perfil.debe_cambiar_clave = True
        perfil.save(update_fields=["debe_cambiar_clave"])
        request.session["clave_nueva"] = [perfil.usuario.get_full_name() or perfil.usuario.username, perfil.rut_fmt, clave]
    return redirect("panel_personas")


@require_POST
@gestor_requerido
def persona_estado(request, pk):
    perfil = _objetivo(request, pk)
    if perfil:
        u = perfil.usuario
        u.is_active = not u.is_active
        u.save(update_fields=["is_active"])
        if not u.is_active:
            _cerrar_jornadas(u)
        messages.success(request, f"La cuenta de {u.get_full_name() or u.username} quedó {'activa' if u.is_active else 'desactivada'}.")
    return redirect("panel_personas")


# ====================== vehículos ======================
@gestor_requerido
def vehiculos(request):
    qs = vehiculos_visibles(request.user)
    pendientes = qs.filter(aprobado=False).count()
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    if q:
        qs = qs.filter(Q(patente__icontains=q.replace(" ", "")) | Q(modelo__icontains=q))
    if estado == "pendientes":
        qs = qs.filter(aprobado=False)
    conductores = list(perfiles_visibles(request.user).filter(rol=COND))
    lista = list(qs.order_by("aprobado", "patente"))
    for v in lista:
        v.asignados = list(v.conductores.all())
        ya = {u.pk for u in v.asignados}
        v.disponibles = [p for p in conductores if p.usuario_id not in ya]
    return render(request, "panel/vehiculos.html", _ctx(
        request, "vehiculos", vehiculos=lista, q=q, estado=estado, pendientes=pendientes))


@gestor_requerido
def vehiculo_form(request, pk=None):
    v = get_object_or_404(vehiculos_visibles(request.user), pk=pk) if pk else None
    rec = recorridos_visibles(request.user)
    if v:
        rec = (rec | Recorrido.objects.filter(pk=v.recorrido_id)).distinct()
    elif not rec.exists():
        messages.error(request, "No tienes recorridos a cargo. Pídele al administrador que te asigne uno.")
        return redirect("panel_vehiculos")
    form = VehiculoForm(request.POST or None, instance=v, recorridos_qs=rec)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "El vehículo se guardó.")
        return redirect("panel_vehiculos")
    return render(request, "panel/vehiculo_form.html", _ctx(request, "vehiculos", form=form, vehiculo=v))


@require_POST
@gestor_requerido
def vehiculo_aprobar(request, pk):
    v = get_object_or_404(vehiculos_visibles(request.user), pk=pk)
    v.aprobado = not v.aprobado
    v.save(update_fields=["aprobado"])
    messages.success(request, f"{v.patente} {'aprobado' if v.aprobado else 'sin aprobar'}.")
    return redirect("panel_vehiculos")


@require_POST
@gestor_requerido
def vehiculo_conductor(request, pk):
    v = get_object_or_404(vehiculos_visibles(request.user), pk=pk)
    uid, accion = request.POST.get("usuario"), request.POST.get("accion")
    if accion == "quitar":
        u = v.conductores.filter(pk=uid).first()
        if u:
            v.conductores.remove(u)
            Jornada.objects.filter(conductor=u, vehiculo=v, fin__isnull=True).update(fin=timezone.now(), lat=None, lng=None)
    elif accion == "agregar":
        p = perfiles_visibles(request.user).filter(rol=COND, usuario_id=uid or 0, usuario__is_active=True).first()
        if p:
            v.conductores.add(p.usuario)
        else:
            messages.error(request, "Ese conductor no está disponible para asignar.")
    return redirect("panel_vehiculos")
