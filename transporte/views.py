import json
import math
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Avg, ProtectedError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import FotoForm, RegistroForm
from .models import Jornada, Perfil, Recorrido, Valoracion, Vehiculo

UBICACION_VIGENTE = timedelta(minutes=2)  # no se muestra una ubicación más antigua
JORNADA_ABANDONADA = timedelta(minutes=30)  # sin señal por tanto tiempo: se considera olvidada y se libera el vehículo


def _json(request):
    try:
        return json.loads(request.body or "{}")
    except ValueError:
        return {}


def _es_conductor(user):
    return user.is_authenticated and getattr(getattr(user, "perfil", None), "rol", "") == Perfil.Rol.CONDUCTOR


def _es_admin(user):
    return user.is_authenticated and (user.is_superuser or getattr(getattr(user, "perfil", None), "rol", "") == Perfil.Rol.ADMIN)


def solo_admin(view):
    @wraps(view)
    def inner(request, *a, **kw):
        if not _es_admin(request.user):
            return JsonResponse({"error": "Solo administradores."}, status=403)
        return view(request, *a, **kw)
    return inner


def solo_conductor(view):
    @wraps(view)
    def inner(request, *a, **kw):
        if not _es_conductor(request.user):
            return JsonResponse({"error": "Solo conductores autorizados."}, status=403)
        return view(request, *a, **kw)
    return inner


# ---------- páginas ----------
def mapa(request):
    return render(request, "mapa.html")


def registro(request):
    form = RegistroForm(request.POST or None)
    if form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            # el RUT es el nombre de usuario: es único, a diferencia del nombre
            user = User.objects.create_user(username=d["rut"], password=d["password1"], first_name=d["nombre"])
            Perfil.objects.create(usuario=user, rol=Perfil.Rol.PASAJERO, rut=d["rut"])  # otros roles: los asigna un administrador
        login(request, user)
        return redirect(reverse("mapa") + "?bienvenida=1")
    return render(request, "registration/registro.html", {"form": form})


@login_required
@require_POST
def subir_foto(request):
    if not _es_conductor(request.user):
        return redirect("mapa")
    form = FotoForm(request.POST, request.FILES)
    if form.is_valid():
        perfil = request.user.perfil
        if perfil.foto:
            perfil.foto.delete(save=False)
        perfil.foto = form.cleaned_data["foto"]
        perfil.save()
        messages.success(request, "Tu foto se actualizó.")
    else:
        messages.error(request, " ".join(form.errors.get("foto", ["No se pudo guardar la foto."])))
    return redirect("conductor")


@login_required
def panel_conductor(request):
    if not _es_conductor(request.user):
        return redirect("mapa")
    jornada = (Jornada.objects.filter(conductor=request.user, fin__isnull=True)
               .select_related("vehiculo__recorrido").first())
    vehiculos = request.user.vehiculos_asignados.filter(aprobado=True).select_related("recorrido")
    return render(request, "conductor.html", {"jornada": jornada, "vehiculos": vehiculos})


# ---------- API pública ----------
def _distancia_m(lat, lng, geo):
    """Distancia mínima (m) desde un punto hasta la línea del recorrido (aprox. plana, válida en una ciudad)."""
    if not geo:
        return None
    kx, ky = 111320 * math.cos(math.radians(lat)), 110540
    pts = [((g[1] - lng) * kx, (g[0] - lat) * ky) for g in geo]
    if len(pts) == 1:
        return math.hypot(*pts[0])
    mejor = float("inf")
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        s = 0 if l2 == 0 else max(0, min(1, -(x1 * dx + y1 * dy) / l2))
        mejor = min(mejor, math.hypot(x1 + s * dx, y1 + s * dy))
    return mejor


def api_recorridos(request):
    """Solo devuelve recorridos si se busca por nombre (q) o se indica una ubicación (lat, lng, radio en metros)."""
    qs = Recorrido.objects.filter(activo=True)
    q = request.GET.get("q", "").strip()
    pos = None
    try:
        if request.GET.get("lat") and request.GET.get("lng"):
            lat, lng = float(request.GET["lat"]), float(request.GET["lng"])
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                pos = (lat, lng)
        radio = max(100, min(int(request.GET.get("radio", 1000)), 20000))
    except ValueError:
        return JsonResponse({"error": "Parámetros inválidos."}, status=400)

    if request.GET.get("todos") and _es_admin(request.user):
        items = [(r, None) for r in qs]
    elif q:
        items = [(r, _distancia_m(*pos, r.geometria) if pos else None) for r in qs.filter(nombre__icontains=q)[:30]]
    elif pos:
        items = []
        for r in qs:
            d = _distancia_m(*pos, r.geometria)
            if d is not None and d <= radio:
                items.append((r, d))
        items.sort(key=lambda x: x[1])
    else:
        items = []
    data = [{"id": r.id, "nombre": r.nombre, "geometria": r.geometria,
             "tarifa": r.tarifa, "tarifa_actualizada": r.tarifa_actualizada,
             "distancia": round(d) if d is not None else None} for r, d in items]
    return JsonResponse({"recorridos": data})


def api_colectivos(request):
    desde = timezone.now() - UBICACION_VIGENTE
    qs = (Jornada.objects.filter(fin__isnull=True, vehiculo__aprobado=True,
                                 lat__isnull=False, actualizado__gte=desde)
          .select_related("conductor__perfil", "vehiculo__recorrido"))
    ids = request.GET.get("recorridos")
    if ids is not None:  # el mapa solo pide los colectivos de los recorridos que está mostrando
        try:
            lista = [int(i) for i in ids.split(",") if i]
        except ValueError:
            lista = []
        qs = qs.filter(vehiculo__recorrido_id__in=lista)
    out = []
    for j in qs:
        prom = Valoracion.objects.filter(jornada__conductor=j.conductor).aggregate(p=Avg("puntaje"))["p"]
        perfil = getattr(j.conductor, "perfil", None)
        foto = perfil.foto.url if perfil and perfil.foto else None
        out.append({
            "jornada": j.id,
            "patente": j.vehiculo.patente,
            "modelo": j.vehiculo.modelo,
            "recorrido": j.vehiculo.recorrido.nombre,
            "foto": foto,
            "conductor": j.conductor.get_full_name() or j.conductor.username,
            "lat": j.lat, "lng": j.lng,
            "hay_asientos": j.asientos_libres > 0,  # nunca se publica la cantidad
            "valoracion": round(prom, 1) if prom else None,
        })
    return JsonResponse({"colectivos": out})


# ---------- API del conductor ----------
@require_POST
@solo_conductor
def api_iniciar(request):
    d = _json(request)
    # solo puede iniciar con un vehículo que el administrador le asignó
    veh = (request.user.vehiculos_asignados.filter(pk=d.get("vehiculo"), aprobado=True, recorrido__activo=True)
           .select_related("recorrido").first())
    if not veh:
        return JsonResponse({"error": "Ese vehículo no está asignado a tu cuenta o aún no está aprobado."}, status=400)
    ahora = timezone.now()
    Jornada.objects.filter(conductor=request.user, fin__isnull=True).update(fin=ahora, lat=None, lng=None)
    ocupado = Jornada.objects.filter(vehiculo=veh, fin__isnull=True).select_related("conductor").first()
    if ocupado:
        if (ocupado.actualizado or ocupado.inicio) < ahora - JORNADA_ABANDONADA:
            Jornada.objects.filter(pk=ocupado.pk).update(fin=ahora, lat=None, lng=None)  # jornada olvidada
        else:
            quien = ocupado.conductor.get_full_name() or ocupado.conductor.username
            return JsonResponse({"error": f"Este vehículo tiene una jornada activa de {quien}. "
                                          "Debe finalizarla antes de que puedas iniciar."}, status=409)
    try:
        j = Jornada.objects.create(conductor=request.user, vehiculo=veh, asientos_libres=veh.capacidad)
    except IntegrityError:
        return JsonResponse({"error": "El vehículo acaba de ser tomado por otro conductor."}, status=409)
    return JsonResponse({"ok": True, "asientos": j.asientos_libres, "capacidad": veh.capacidad})


@require_POST
@solo_conductor
def api_actualizar(request):
    j = Jornada.objects.filter(conductor=request.user, fin__isnull=True).select_related("vehiculo").first()
    if not j:
        return JsonResponse({"error": "No tienes una jornada iniciada."}, status=400)
    d = _json(request)
    try:
        if "lat" in d and "lng" in d:
            lat, lng = float(d["lat"]), float(d["lng"])
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError
            j.lat, j.lng = lat, lng
        if "asientos" in d:
            j.asientos_libres = max(0, min(int(d["asientos"]), j.vehiculo.capacidad))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    j.actualizado = timezone.now()
    j.save()
    return JsonResponse({"ok": True, "asientos": j.asientos_libres})


@require_POST
@solo_conductor
def api_finalizar(request):
    Jornada.objects.filter(conductor=request.user, fin__isnull=True).update(fin=timezone.now(), lat=None, lng=None)
    return JsonResponse({"ok": True})


# ---------- valoración ----------
@require_POST
def api_valorar(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión para valorar."}, status=403)
    d = _json(request)
    jornada = Jornada.objects.filter(pk=d.get("jornada")).first()
    try:
        puntaje = int(d.get("puntaje"))
    except (TypeError, ValueError):
        puntaje = 0
    if not jornada or not 1 <= puntaje <= 5 or d.get("categoria") not in Valoracion.Categoria.values:
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    Valoracion.objects.update_or_create(
        jornada=jornada, pasajero=request.user,
        defaults={"puntaje": puntaje, "categoria": d["categoria"],
                  "comentario": str(d.get("comentario", ""))[:500], "revisada": False})
    return JsonResponse({"ok": True})


# ---------- administración de recorridos ----------
@login_required
def gestion_recorridos(request):
    if not _es_admin(request.user):
        return redirect("mapa")
    return render(request, "gestion_recorridos.html", {"recorridos": Recorrido.objects.order_by("nombre")})


@require_POST
@solo_admin
def api_guardar_recorrido(request):
    d = _json(request)
    nombre = str(d.get("nombre", "")).strip()[:120]
    try:
        tarifa = int(d.get("tarifa") or 0)
        geo = [[float(p[0]), float(p[1])] for p in d.get("geometria", [])]
    except (TypeError, ValueError, IndexError):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    if not nombre or tarifa < 0:
        return JsonResponse({"error": "Completa el nombre y una tarifa válida."}, status=400)
    if not 2 <= len(geo) <= 20000 or any(not (-90 <= a <= 90 and -180 <= b <= 180) for a, b in geo):
        return JsonResponse({"error": "El recorrido necesita al menos 2 puntos válidos en el mapa."}, status=400)
    r = Recorrido.objects.create(nombre=nombre, geometria=geo,
                                 tarifa=tarifa, tarifa_actualizada=timezone.localdate())
    return JsonResponse({"ok": True, "id": r.id})


@require_POST
@solo_admin
def api_eliminar_recorrido(request):
    r = Recorrido.objects.filter(pk=_json(request).get("id")).first()
    if not r:
        return JsonResponse({"error": "El recorrido no existe."}, status=404)
    try:
        r.delete()
    except ProtectedError:
        return JsonResponse({"error": "No se puede eliminar: tiene vehículos asignados."}, status=400)
    return JsonResponse({"ok": True})
