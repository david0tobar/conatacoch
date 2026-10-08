# Conatacoch

Proyecto Django: colectivos en tiempo real sobre mapa real (Leaflet + OpenStreetMap).

## Puesta en marcha
```
pip install -r requirements.txt
python manage.py makemigrations transporte
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Primeros datos (desde /admin)
1. Crear un **Recorrido** (la geometría es una lista `[[lat, lng], ...]`).
2. Crear un **Vehículo** y marcarlo como aprobado.
3. Crear un usuario y, en **Perfiles**, asignarle el rol `conductor`.
4. Entrar como conductor en `/conductor/`, iniciar la jornada y abrir `/` en otro navegador.

## Reglas del informe que ya cumple
- El colectivo solo aparece con jornada activa y ubicación de menos de 2 minutos.
- Al finalizar la jornada se borra la ubicación.
- Al público solo se le informa si **hay asientos**, nunca la cantidad.
- Valoración de 1 a 5 con categoría y comentario, una por usuario y servicio, sin sanciones automáticas.
- Roles: pasajero, conductor, representante y administrador.

## Pendiente (siguientes sprints)
- Importar recorridos desde las planillas Excel (HU-12).
- Señal de espera del pasajero y vista de demanda para el conductor.
- Tiempo estimado de llegada, estadísticas y panel del representante.
- Cambiar el polling (4 s) por WebSockets con Django Channels + Redis.
