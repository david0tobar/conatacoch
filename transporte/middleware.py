from django.http import JsonResponse
from django.shortcuts import redirect


class CambioClaveObligatorio:
    """Quien tiene una contraseña provisoria debe cambiarla antes de usar el sistema."""
    PERMITIDAS = ("/cambiar-clave/", "/logout/", "/static/", "/media/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = request.user
        if u.is_authenticated and not request.path.startswith(self.PERMITIDAS):
            perfil = getattr(u, "perfil", None)
            if perfil and perfil.debe_cambiar_clave:
                if request.path.startswith("/api/"):
                    return JsonResponse({"error": "Debes cambiar tu contraseña."}, status=403)
                return redirect("cambiar_clave")
        return self.get_response(request)
