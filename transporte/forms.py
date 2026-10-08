from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
import re

from django.core.exceptions import ValidationError

from .models import Perfil, Recorrido, Vehiculo
from .rut import es_valido, normalizar


class RegistroForm(forms.Form):
    rut = forms.CharField(label="RUT", max_length=12, help_text="Ejemplo: 12.345.678-5")
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Repite la contraseña", widget=forms.PasswordInput)

    def clean_rut(self):
        rut = normalizar(self.cleaned_data["rut"])
        if not es_valido(rut):
            raise ValidationError("El RUT no es válido. Revisa el número y el dígito verificador.")
        if User.objects.filter(username=rut).exists() or Perfil.objects.filter(rut=rut).exists():
            raise ValidationError("Ya existe una cuenta con este RUT.")
        return rut

    def clean(self):
        datos = super().clean()
        p1, p2 = datos.get("password1"), datos.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        elif p1:
            try:
                validate_password(p1)
            except ValidationError as e:
                self.add_error("password1", e)
        return datos


class LoginForm(AuthenticationForm):
    """Se ingresa con el RUT (con o sin puntos y guion)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "RUT"

    def clean_username(self):
        u = self.cleaned_data["username"].strip()
        rut = normalizar(u)
        return rut if es_valido(rut) else u  # permite cuentas creadas por el admin de Django


class FotoForm(forms.Form):
    foto = forms.ImageField(label="Foto")

    def clean_foto(self):
        f = self.cleaned_data["foto"]
        if f.size > 2 * 1024 * 1024:
            raise ValidationError("La imagen no puede pesar más de 2 MB.")
        return f


def _validar_foto(f):
    if f and f.size > 2 * 1024 * 1024:
        raise ValidationError("La imagen no puede pesar más de 2 MB.")
    return f


class PersonaForm(forms.Form):
    rut = forms.CharField(label="RUT", max_length=12, help_text="Ejemplo: 12.345.678-5")
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    rol = forms.ChoiceField(label="Rol", choices=[])
    foto = forms.ImageField(label="Foto", required=False)
    vehiculos = forms.ModelMultipleChoiceField(label="Vehículos que puede manejar", queryset=Vehiculo.objects.none(),
                                               required=False, widget=forms.CheckboxSelectMultiple)
    representante = forms.ModelChoiceField(label="Representante legal responsable", queryset=User.objects.none(),
                                           required=False, empty_label="Sin representante")
    recorridos = forms.ModelMultipleChoiceField(label="Recorridos a cargo", queryset=Recorrido.objects.none(),
                                                required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, es_admin, crear, vehiculos_qs, recorridos_qs, bloquear_rol=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.crear = crear
        self.fields["rol"].choices = list(Perfil.Rol.choices) if es_admin else [(Perfil.Rol.CONDUCTOR, "Conductor")]
        if not es_admin:
            self.fields["rol"].initial = Perfil.Rol.CONDUCTOR
        # un representante solo crea conductores; nadie cambia su propio rol ni el de un superusuario
        self.fields["rol"].disabled = bloquear_rol or not es_admin
        if not crear:
            del self.fields["rut"]
        self.fields["vehiculos"].queryset = vehiculos_qs
        self.fields["vehiculos"].label_from_instance = lambda v: f"{v.patente} · {v.modelo}"
        if es_admin:
            self.fields["representante"].queryset = User.objects.filter(perfil__rol=Perfil.Rol.REPRESENTANTE, is_active=True)
            self.fields["representante"].label_from_instance = lambda u: u.get_full_name() or u.username
            self.fields["recorridos"].queryset = recorridos_qs
        else:
            del self.fields["representante"], self.fields["recorridos"]

    def clean_rut(self):
        rut = normalizar(self.cleaned_data["rut"])
        if not es_valido(rut):
            raise ValidationError("El RUT no es válido. Revisa el número y el dígito verificador.")
        if User.objects.filter(username=rut).exists() or Perfil.objects.filter(rut=rut).exists():
            raise ValidationError("Ya existe una cuenta con este RUT.")
        return rut

    def clean_foto(self):
        return _validar_foto(self.cleaned_data.get("foto"))


class VehiculoForm(forms.ModelForm):
    class Meta:
        model = Vehiculo
        fields = ["patente", "modelo", "capacidad", "recorrido", "aprobado"]
        labels = {"aprobado": "Aprobado (visible para los pasajeros)"}

    def __init__(self, *args, recorridos_qs, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recorrido"].queryset = recorridos_qs
        self.fields["recorrido"].empty_label = "Elige un recorrido"
        self.fields["patente"].help_text = "Ejemplo: BBCD12 o AB1234"

    def clean_patente(self):
        p = re.sub(r"[^A-Za-z0-9]", "", self.cleaned_data["patente"]).upper()
        if not re.fullmatch(r"[A-Z]{2}\d{4}|[A-Z]{4}\d{2}", p):
            raise ValidationError("La patente no es válida. Usa el formato BBCD12 o AB1234.")
        return p

    def clean_capacidad(self):
        c = self.cleaned_data["capacidad"]
        if not 1 <= c <= 60:
            raise ValidationError("La capacidad debe estar entre 1 y 60 asientos.")
        return c
