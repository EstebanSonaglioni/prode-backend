from django.db import models
from django.contrib.auth.models import User # Usamos el modelo de usuario por defecto de Django

class Prode(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    codigo_invitacion = models.CharField(max_length=20, unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='prodes_creados')
    privado = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class Partido(models.Model):
    equipo_local = models.CharField(max_length=100)
    equipo_visitante = models.CharField(max_length=100)
    fecha_partido = models.DateTimeField()
    goles_local_real = models.IntegerField(blank=True, null=True)
    goles_visitante_real = models.IntegerField(blank=True, null=True)
    
    ESTADO_CHOICES = [
        ('programado', 'Programado'),
        ('en_curso', 'En Curso'),
        ('finalizado', 'Finalizado'),
    ]
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='programado')

    def __str__(self):
        return f"{self.equipo_local} vs {self.equipo_visitante}"

class Prediccion(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    prode = models.ForeignKey(Prode, on_delete=models.CASCADE, related_name='predicciones')
    partido = models.ForeignKey(Partido, on_delete=models.CASCADE)
    goles_local = models.IntegerField()
    goles_visitante = models.IntegerField()
    puntos_ganados = models.IntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Esto implementa el UNIQUE que hablamos para evitar duplicados
        unique_together = ('usuario', 'prode', 'partido')

    def __str__(self):
        return f"{self.usuario.username} - {self.partido}"