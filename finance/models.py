from django.db import models
from django.conf import settings


class ConceptoIngreso(models.Model):
    TIPO_CHOICES = [
        ("INGRESO", "Ingreso"),
        ("EGRESO", "Egreso"),
    ]
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default="INGRESO", verbose_name="Tipo")
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    monto_defecto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)
    no_eliminar = models.BooleanField(default=False, verbose_name="No eliminar",
        help_text="Protegido contra eliminación desde el listado")
    requiere_jugador = models.BooleanField(default=False, verbose_name="Requiere jugador", help_text="Mostrar campo jugador en POS cuando se seleccione este concepto")
    requiere_equipo = models.BooleanField(default=False, verbose_name="Requiere equipo", help_text="Obligar a seleccionar un equipo en POS")
    requiere_categoria = models.BooleanField(default=False, verbose_name="Requiere categoría/temporada",
        help_text="En POS pedirá categoría y temporada activa antes del equipo")
    excluir_pagados = models.BooleanField(default=False, verbose_name="Excluir pagados",
        help_text="En POS, al filtrar por temporada, oculta equipos que ya pagaron este concepto en esa temporada")
    categoria = models.ForeignKey(
        "league.Categoria", on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Categoría (filtro)",
        help_text="Si se asigna, en POS filtra solo esta categoría (dejar vacío para todas)"
    )

    class Meta:
        verbose_name = "Concepto"
        verbose_name_plural = "Conceptos"

    def __str__(self):
        return self.nombre

    def es_ingreso(self):
        return self.tipo == "INGRESO"


class Ingreso(models.Model):
    concepto = models.ForeignKey(
        ConceptoIngreso, on_delete=models.CASCADE, related_name="ingresos"
    )
    monto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total")
    cantidad = models.PositiveIntegerField(default=1, verbose_name="Cantidad",
        help_text="Número de unidades (ej: 3 arbitrajes)")
    fecha = models.DateField()
    equipo = models.ForeignKey(
        "league.Equipo", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ingresos"
    )
    temporada = models.ForeignKey(
        "league.Temporada", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ingresos"
    )
    jugador = models.ForeignKey(
        "league.Jugador", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ingresos"
    )
    descripcion = models.TextField(blank=True)
    pagado_a = models.CharField(max_length=200, blank=True, verbose_name="Pagado a",
        help_text="Nombre del proveedor o persona a quien se pagó (solo egresos)")
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="ingresos"
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"
        ordering = ["-fecha_registro"]

    def __str__(self):
        return f"{self.concepto.nombre} - ${self.monto}"

    @property
    def es_ingreso(self):
        return self.concepto.es_ingreso()

    @property
    def precio_unitario(self):
        if self.cantidad > 0:
            return self.monto / self.cantidad
        return 0
