import uuid
from django.db import models, ProgrammingError
from django.db.models import Manager
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from PIL import Image


class CategoriaQuerySet(models.QuerySet):
    def _fetch_all(self):
        try:
            super()._fetch_all()
        except ProgrammingError as e:
            if "does not exist" in str(e) and "fondo_credencial" in str(e):
                from django.db import connection
                with connection.cursor() as cur:
                    cur.execute("ALTER TABLE league_categoria ADD COLUMN IF NOT EXISTS fondo_credencial varchar(200) NOT NULL DEFAULT ''")
                super()._fetch_all()
            else:
                raise


class CategoriaManager(Manager):
    def get_queryset(self):
        return CategoriaQuerySet(self.model, using=self._db)


class Categoria(models.Model):
    objects = CategoriaManager()
    DIAS_SEMANA = [
        ("LUN", "Lunes"), ("MAR", "Martes"), ("MIE", "Miércoles"),
        ("JUE", "Jueves"), ("VIE", "Viernes"), ("SAB", "Sábado"),
        ("DOM", "Domingo"),
    ]
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    rango_edad = models.CharField(max_length=50, blank=True)
    edad_minima = models.IntegerField(null=True, blank=True, verbose_name="Edad mínima",
        help_text="Edad mínima requerida (dejar vacío si no aplica)")
    edad_maxima = models.IntegerField(null=True, blank=True, verbose_name="Edad máxima",
        help_text="Edad máxima permitida (dejar vacío si no aplica)")
    genero = models.CharField(max_length=20, blank=True)
    nivel = models.PositiveIntegerField(null=True, blank=True,
        verbose_name="Nivel (ascenso/descenso)",
        help_text="Orden de la escalera: 1 es la categoría más alta (ej. Primera), 2 la siguiente (Intermedia), 3 la más baja (Segunda). Se usa para ascensos/descensos.")
    activo = models.BooleanField(default=True)
    es_principal = models.BooleanField(default=False)
    curp_obligatoria = models.BooleanField(default=False, verbose_name="CURP obligatoria",
        help_text="Si está activa, el CURP será obligatorio al registrar jugadores en esta categoría.")
    min_jugadores = models.IntegerField(default=7, verbose_name="Mínimo de jugadores por equipo")
    max_jugadores = models.IntegerField(default=26, verbose_name="Máximo de jugadores por equipo")
    dias_juego = models.JSONField(default=list, blank=True, verbose_name="Días de juego")
    horarios = models.JSONField(default=list, blank=True, verbose_name="Horarios (HH:MM)")
    categorias_compatibles = models.ManyToManyField(
        "self", symmetrical=False, blank=True,
        verbose_name="Categorías compatibles",
        help_text="Jugadores de esta categoría también pueden registrarse en las categorías seleccionadas."
    )
    campos_permitidos = models.ManyToManyField(
        "Campo", blank=True, related_name="categorias_permitidas",
        verbose_name="Campos permitidos",
        help_text="Únicos campos donde puede jugar esta categoría. Si no seleccionas ninguno, puede jugar en cualquier campo."
    )
    fondo_credencial = models.ImageField(
        upload_to="fondos_credencial/", blank=True, null=True,
        verbose_name="Fondo para credenciales",
        help_text="Imagen de fondo que aparecerá en las credenciales de esta categoría."
    )

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

    def __str__(self):
        return self.nombre

    def _escalera_qs(self):
        return Categoria.objects.filter(activo=True, genero=self.genero)

    def categoria_superior(self):
        """Categoría inmediatamente superior (nivel - 1), o None si es la más alta."""
        if self.nivel is None:
            return None
        return self._escalera_qs().filter(nivel=self.nivel - 1).first()

    def categoria_inferior(self):
        """Categoría inmediatamente inferior (nivel + 1), o None si es la más baja."""
        if self.nivel is None:
            return None
        return self._escalera_qs().filter(nivel=self.nivel + 1).first()

    def save(self, *args, **kwargs):
        if self.es_principal:
            Categoria.objects.filter(es_principal=True).exclude(pk=self.pk).update(es_principal=False)
        super().save(*args, **kwargs)


class Equipo(models.Model):
    nombre = models.CharField(max_length=100)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.CASCADE, related_name="equipos"
    )
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)
    activo = models.BooleanField(default=True)
    campo_rancheria = models.ForeignKey(
        "Campo", on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Campo ranchería",
        help_text="Si es equipo de ranchería, selecciona su campo. Cuando sea local se asignará automáticamente."
    )

    class Meta:
        verbose_name = "Equipo"
        verbose_name_plural = "Equipos"
        unique_together = ["nombre", "categoria"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.logo:
            try:
                img = Image.open(self.logo.path)
                if max(img.width, img.height) > 300:
                    img.thumbnail((300, 300), Image.Lanczos)
                    img.save(self.logo.path, optimize=True, quality=85)
            except Exception:
                pass

    def __str__(self):
        return f"{self.nombre} ({self.categoria.nombre})"


class JugadorEquipo(models.Model):
    jugador = models.ForeignKey(
        "Jugador", on_delete=models.CASCADE, related_name="registros_equipo"
    )
    equipo = models.ForeignKey(
        "Equipo", on_delete=models.CASCADE, related_name="registros_jugador"
    )
    es_principal = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    fecha_alta = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "Registro Jugador-Equipo"
        verbose_name_plural = "Registros Jugador-Equipo"
        unique_together = ["jugador", "equipo"]

    def __str__(self):
        return f"{self.jugador} -> {self.equipo}"


class Jugador(models.Model):
    POSICIONES = [
        ("POR", "Portero"),
        ("DEF", "Defensa"),
        ("MED", "Mediocampista"),
        ("DEL", "Delantero"),
    ]
    TIPOS_DOCUMENTO = [
        ("CURP", "CURP"),
        ("PAS", "Pasaporte"),
        ("INM", "Cédula INM / Residencia"),
        ("OTR", "Otro"),
    ]
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    tipo_documento = models.CharField(max_length=4, choices=TIPOS_DOCUMENTO, default="CURP",
        verbose_name="Tipo de documento",
        help_text="CURP para mexicanos. Para extranjeros: Pasaporte o Cédula INM.")
    curp = models.CharField(max_length=18, unique=True, blank=True, null=True,
        verbose_name="Número de documento",
        help_text="CURP (18 caracteres) o número de pasaporte/INM según el tipo.")
    foto = models.ImageField(upload_to="jugadores/", blank=True, null=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    posicion = models.CharField(max_length=3, choices=POSICIONES)
    equipo = models.ForeignKey(
        Equipo, on_delete=models.CASCADE, related_name="jugadores",
        blank=True, null=True,
        help_text="Equipo principal. Puede dejarse vacío si el jugador aún no tiene equipo asignado.",
    )
    equipos = models.ManyToManyField(
        Equipo, through=JugadorEquipo, blank=True,
        related_name="jugadores_m2m",
        verbose_name="Equipos (compatibles)",
    )
    dorsal = models.IntegerField(blank=True, null=True)
    activo = models.BooleanField(default=True)
    suspendido_pago = models.BooleanField(default=False, verbose_name="Suspendido por multa",
        help_text="Suspendido por multa de edad. Se levanta al registrar el pago.")

    class Meta:
        verbose_name = "Jugador"
        verbose_name_plural = "Jugadores"

    def edad(self):
        if not self.fecha_nacimiento:
            return None
        from datetime import date
        hoy = date.today()
        return hoy.year - self.fecha_nacimiento.year - (
            (hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day)
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Sincronizar equipo principal con JugadorEquipo
        if self.equipo and not self.registros_equipo.filter(equipo=self.equipo, es_principal=True).exists():
            JugadorEquipo.objects.get_or_create(
                jugador=self,
                equipo=self.equipo,
                defaults={"es_principal": True},
            )
        if self.foto:
            try:
                img = Image.open(self.foto.path)
                if max(img.width, img.height) > 400:
                    img.thumbnail((400, 400), Image.Lanczos)
                    img.save(self.foto.path, optimize=True, quality=85)
            except Exception:
                pass

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class Campo(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=255, blank=True)
    telefono_contacto = models.CharField(max_length=20, blank=True)
    precio_hora = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    es_rancheria = models.BooleanField(default=False, verbose_name="Es ranchería")
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True, verbose_name="Observaciones")
    fecha_estimada_retorno = models.DateField(blank=True, null=True, verbose_name="Fecha estimada de retorno")

    class Meta:
        verbose_name = "Campo"
        verbose_name_plural = "Campos"

    def __str__(self):
        return self.nombre


class Arbitro(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, blank=True)
    activo = models.BooleanField(default=True)
    usuario = models.OneToOneField(
        "accounts.Usuario", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="perfil_arbitro",
    )

    class Meta:
        verbose_name = "Árbitro"
        verbose_name_plural = "Árbitros"

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"


class HorarioFijoEquipo(models.Model):
    temporada = models.ForeignKey(
        "Temporada", on_delete=models.CASCADE, related_name="horarios_fijos"
    )
    equipo = models.ForeignKey(
        Equipo, on_delete=models.CASCADE, related_name="horarios_fijos"
    )
    horario = models.CharField(max_length=5, verbose_name="Horario (HH:MM)")

    class Meta:
        verbose_name = "Horario Fijo de Equipo"
        verbose_name_plural = "Horarios Fijos de Equipos"
        unique_together = ["temporada", "equipo"]

    def __str__(self):
        return f"{self.equipo.nombre} - {self.horario} ({self.temporada.nombre})"


class Temporada(models.Model):
    TIPOS_ROL = [
        ("TODOS", "Todos contra Todos"),
        ("GRUPOS", "Por Grupos"),
    ]
    TIPOS_COMPETENCIA = [
        ("PUNTOS", "Por puntos (más puntos gana)"),
        ("LIGUILLA", "Liguilla (clasifican los mejores)"),
    ]
    nombre = models.CharField(max_length=100)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.CASCADE, related_name="temporadas"
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(blank=True, null=True)
    iniciada = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)
    tipo_rol = models.CharField(max_length=10, choices=TIPOS_ROL, default="TODOS", verbose_name="Tipo de rol")
    vueltas = models.IntegerField(default=1, verbose_name="Número de vueltas")
    num_grupos = models.IntegerField(default=0, verbose_name="Número de grupos (solo para Por Grupos)")
    tipo_competencia = models.CharField(max_length=10, choices=TIPOS_COMPETENCIA, default="PUNTOS", verbose_name="Tipo de competencia")
    num_clasificados = models.IntegerField(default=8, verbose_name="Clasificados a liguilla (solo para Liguilla)")
    es_prueba = models.BooleanField(default=False, verbose_name="Modo prueba")
    jornadas_limite_pago = models.IntegerField(
        null=True, blank=True, verbose_name="Jornadas límite para pago de inscripción",
        help_text="Si un equipo no ha pagado la inscripción después de esta jornada, pierde por default hasta que pague."
    )
    goles_default = models.IntegerField(
        default=3, verbose_name="Goles por default",
        help_text="Goles que se le asignan al equipo que gana por default (ej. 3-0)."
    )
    puntos_default = models.IntegerField(
        default=3, verbose_name="Puntos que pierde por derrota default",
        help_text="Puntos que se restan al equipo que pierde un partido por default (mora, abandono o alineación indebida). Ej. 3 = -3 puntos en la tabla por cada partido perdido por default."
    )
    min_jugadores = models.IntegerField(
        default=7, verbose_name="Mínimo de jugadores por equipo",
        help_text="Número mínimo de jugadores que debe tener un equipo en cédula para poder jugar. Si no se cumple, solo se puede guardar como Default."
    )
    cambios_permitidos = models.IntegerField(
        null=True, blank=True, default=5, verbose_name="Cambios permitidos por equipo",
        help_text="Máximo de cambios (suplentes) permitidos por equipo por partido. Déjalo en blanco o pon 0 para no limitar los cambios (sin restricción)."
    )
    max_titulares = models.IntegerField(
        default=11, verbose_name="Máximo de titulares por equipo",
        help_text="Número máximo de jugadores titulares permitidos por equipo en la cédula. Si se excede, el partido se pierde por default por alineación indebida."
    )
    ida_vuelta = models.BooleanField(default=False, verbose_name="Liguilla a ida y vuelta",
        help_text="Si está activo, los cruces de liguilla serán a dos partidos (ida y vuelta).")
    final_ida_vuelta = models.BooleanField(default=False, verbose_name="Final a ida y vuelta",
        help_text="Si está activo, la final será a dos partidos (ida y vuelta).")
    gol_visitante_desempate = models.BooleanField(default=False, verbose_name="Gol de visitante como desempate",
        help_text="Usa los goles como visitante como 4° criterio de desempate en la tabla general.")
    posicion_tabla_desempate = models.BooleanField(default=False, verbose_name="Enfrentamiento directo como desempate",
        help_text="Si hay empate en todos los criterios, se usa el resultado del partido entre los equipos empatados.")
    criterio_liguilla = models.CharField(
        max_length=20, blank=True, null=True,
        choices=[("gol_visitante", "Gol de visitante"), ("posicion_tabla", "Posición en la tabla")],
        verbose_name="Criterio de desempate en liguilla",
        help_text="Si hay empate global en una serie de liguilla, ¿qué criterio usar para definir al ganador?"
    )
    min_porcentaje_liguilla = models.IntegerField(
        null=True, blank=True, verbose_name="% mínimo de juegos para liguilla",
        help_text="Porcentaje de partidos de temporada regular que un jugador debe haber jugado para ser elegible en liguilla. Vacío = sin restricción."
    )
    finalizada = models.BooleanField(default=False, verbose_name="Finalizada")
    clasificacion_por_grupos = models.BooleanField(default=False, verbose_name="Clasificar por grupos",
        help_text="Si está activo, clasifican los mejores de cada grupo en lugar de la tabla general. Solo aplica cuando el rol es 'Por Grupos'.")
    fecha_finalizacion = models.DateField(blank=True, null=True, verbose_name="Fecha de finalización")
    motivo_finalizacion = models.TextField(blank=True, verbose_name="Motivo de finalización")
    num_ascensos = models.PositiveIntegerField(
        default=2, verbose_name="Equipos que ascienden",
        help_text="Cuántos equipos suben de categoría al finalizar esta temporada (campeón + los mejores del lugar)."
    )
    num_descensos = models.PositiveIntegerField(
        default=2, verbose_name="Equipos que descienden",
        help_text="Cuántos equipos bajan de categoría al finalizar esta temporada (los últimos lugares de la tabla)."
    )
    aplicar_movimientos = models.BooleanField(
        default=True, verbose_name="Aplicar reglas de ascenso/descenso",
        help_text="Si está activo, al finalizar la temporada se piden los movimientos (sube/baja/desaparece) y se aplican las restricciones a los jugadores. Desactívalo cuando no se quiera mover equipos."
    )

    class Meta:
        verbose_name = "Temporada"
        verbose_name_plural = "Temporadas"

    def __str__(self):
        return f"{self.nombre} - {self.categoria.nombre}"

    def save(self, *args, **kwargs):
        if not self.fecha_fin:
            estimada = self.calcular_fecha_fin_estimada()
            if estimada != self.fecha_inicio:
                self.fecha_fin = estimada
        super().save(*args, **kwargs)

    def actualizar_fecha_fin(self):
        """Ajusta fecha_fin al último partido de la temporada (jornada o liguilla)"""
        ultimo = Partido.objects.filter(temporada=self).order_by("-fecha_hora").first()
        if ultimo:
            nueva = ultimo.fecha_hora.date()
            if self.fecha_fin != nueva:
                self.fecha_fin = nueva
                Temporada.objects.filter(pk=self.pk).update(fecha_fin=self.fecha_fin)

    def equipos_habilitados(self):
        """Equipos activos de la categoría para esta temporada"""
        from .models import Equipo
        return list(Equipo.objects.filter(categoria=self.categoria, activo=True))

    def equipos_descansan(self, jornada):
        """Equipos habilitados de la temporada que descansan en la jornada
        (no tienen ningún partido asignado en ella, sin importar su estado)."""
        from .models import Partido
        ids_jugaron = set(
            Partido.objects.filter(jornada=jornada).values_list("equipo_local_id", flat=True)
        )
        ids_jugaron.update(
            Partido.objects.filter(jornada=jornada).values_list("equipo_visitante_id", flat=True)
        )
        return [eq for eq in self.equipos_habilitados() if eq.id not in ids_jugaron]

    def equipos_pagados(self):
        """Equipos que ya pagaron inscripción para esta temporada"""
        return self._equipos_con_pago()

    def equipo_en_mora(self, equipo):
        """True si el equipo debe la inscripción y ya pasó la jornada límite"""
        if equipo in self.equipos_pagados():
            return False
        if not self.jornadas_limite_pago:
            return False
        return self.jornada_actual() >= self.jornadas_limite_pago

    def equipo_abandono(self, equipo):
        """True si el equipo abandonó la temporada"""
        return AbandonoTemporada.objects.filter(temporada=self, equipo=equipo).exists()

    def equipo_debe_partido(self, equipo):
        """True si el equipo debe perder por default (mora o abandono)"""
        return self.equipo_en_mora(equipo) or self.equipo_abandono(equipo)

    def limite_cambios_efectivo(self):
        """Cambios permitidos por equipo por partido; None si no hay límite (0 o vacío)."""
        c = self.cambios_permitidos
        return c if (c or 0) > 0 else None

    def grupos_asignados(self):
        """Retorna dict {nombre_grupo: [equipos]}"""
        from collections import defaultdict
        grupos = defaultdict(list)
        for g in Grupo.objects.filter(temporada=self).order_by("grupo", "orden"):
            grupos[g.grupo].append(g.equipo)
        return dict(grupos)

    def auto_asignar_grupos(self):
        """Distribuye equipos parejamente en los grupos"""
        equipos = self.equipos_habilitados()
        n = self.num_grupos
        if n < 2:
            return
        Grupo.objects.filter(temporada=self).delete()
        import random
        random.shuffle(equipos)
        for i, eq in enumerate(equipos):
            letra = chr(65 + (i % n))
            Grupo.objects.create(temporada=self, equipo=eq, grupo=letra, orden=i)

    def puede_iniciar(self):
        from .models import Equipo, Jugador, Campo
        eqs = self.equipos_habilitados()
        eq_count = len(eqs)
        if eq_count < 2:
            return False, "Se necesitan al menos 2 equipos activos en la categoría"
        min_jug = self.categoria.min_jugadores or 7
        for eq in eqs:
            # Un equipo marcado como abandono no bloquea el inicio por falta de jugadores
            if self.equipo_abandono(eq):
                continue
            cnt = Jugador.objects.filter(equipo=eq, activo=True).count()
            if cnt < min_jug:
                return False, f"El equipo '{eq.nombre}' solo tiene {cnt} jugadores (mínimo {min_jug})"
        cp = Campo.objects.filter(activo=True).count()
        if cp == 0:
            return False, "Se necesita al menos 1 campo activo"
        return True, "OK"

    def _equipos_con_pago(self):
        from .models import Equipo
        from finance.models import Ingreso
        eqs = Equipo.objects.filter(categoria=self.categoria, activo=True)
        ids_pagados = Ingreso.objects.filter(
            temporada=self,
            equipo__in=eqs,
            concepto__nombre="Inscripción de Equipo",
        ).values_list("equipo_id", flat=True).distinct()
        return [eq for eq in eqs if eq.id in ids_pagados]

    def _generar_fixture_round_robin(self, equipos_list):
        """Genera fixture round-robin para una lista de equipos. Retorna [(local, visit), ...] por ronda"""
        equipos = list(equipos_list)
        n = len(equipos)
        if n % 2 != 0:
            equipos.append(None)
            n = len(equipos)
        fixture = []
        for ronda in range(n - 1):
            ronda_partidos = []
            for i in range(n // 2):
                local = equipos[i]
                visit = equipos[n - 1 - i]
                if local and visit:
                    if ronda % 2 == 0:
                        ronda_partidos.append((local, visit))
                    else:
                        ronda_partidos.append((visit, local))
            fixture.append(ronda_partidos)
            equipos.insert(1, equipos.pop())
        return fixture

    def _crear_partidos_desde_fixture(self, fixture, horarios_fijos, todas_campos, fecha_base, dias_juego, horarios, idx_start=1, jornada_inicial=1, fecha_base_futura=None):
        """Crea TODAS las jornadas y partidos desde un fixture, retorna el último índice usado.

        jornada_inicial: umbral para las fechas. Las jornadas con número menor se
        generan con fecha_base (fecha de inicio, normalmente pasada) para que el
        usuario capture cédulas/goles/castigos; desde jornada_inicial en adelante se
        usan fecha_base_futura (próximo día de juego real).
        """
        from itertools import cycle
        import datetime
        from django.utils import timezone
        mapa_dias = {"LUN": 0, "MAR": 1, "MIE": 2, "JUE": 3, "VIE": 4, "SAB": 5, "DOM": 6}
        num_campos = len(todas_campos)

        # Colectar todos los equipos participantes para tracking de uso de campos
        equipos_set = set()
        for ronda in fixture:
            for item in ronda:
                local, visit = item[0], item[1]
                equipos_set.add(local.id)
                equipos_set.add(visit.id)
        # team_uso_campo[team_id][campo_id] = veces que jugó ahí
        team_uso_campo = {eid: {c.id: 0 for c in todas_campos} for eid in equipos_set}

        # Cache de ocupación cross-temporada: {(fecha_hora, campo_id)}
        ocupados_externos = set(
            Partido.objects.filter(estado__in=["PEND", "SUSP"])
            .exclude(temporada=self)
            .values_list("fecha_hora", "campo_id")
        )
        # Cache de partidos recién creados en este batch
        nuevos_ocupados = set()

        idx = idx_start
        for partidos_ronda in fixture:
            base_usada = fecha_base
            base_idx = 1
            if fecha_base_futura and idx >= jornada_inicial:
                base_usada = fecha_base_futura
                base_idx = jornada_inicial
            jornada = Jornada.objects.create(
                temporada=self,
                numero=idx,
                nombre=f"Jornada {idx}"
            )

            fecha_jornada = base_usada
            if dias_juego:
                dias_validos = sorted([mapa_dias[d] for d in dias_juego if d in mapa_dias])
                if dias_validos:
                    cursor = base_usada + datetime.timedelta(weeks=(idx - base_idx) // len(dias_validos))
                    dia_semana = cursor.weekday()
                    for d in dias_validos:
                        if d >= dia_semana:
                            dias_avance = d - dia_semana
                            break
                    else:
                        dias_avance = (7 - dia_semana) + dias_validos[0]
                    fecha_jornada = cursor + datetime.timedelta(days=dias_avance)

            horarios_cycle = cycle(horarios) if horarios else cycle(["12:00"])
            # Separar campos: rancherías se asignan a equipos con campo_rancheria
            campos_normales = [c for c in todas_campos if not c.es_rancheria]
            campos_rancheria = {c.id: c for c in todas_campos if c.es_rancheria}
            uso_campos_jornada = {c.id: 0 for c in todas_campos}
            for i, item in enumerate(partidos_ronda):
                if len(item) == 3:
                    local, visit, grupo_letra = item
                else:
                    local, visit = item
                    grupo_letra = ""

                # Determinar hora primero (necesitamos fecha_hora para checar conflicto de campo)
                hora_local = None
                if local and local.id in horarios_fijos:
                    hora_local = horarios_fijos[local.id]
                elif visit and visit.id in horarios_fijos:
                    hora_local = horarios_fijos[visit.id]
                if not hora_local:
                    hora_local = next(horarios_cycle)
                try:
                    hh, mm = hora_local.split(":")
                    fecha_hora_partido = datetime.datetime.combine(fecha_jornada, datetime.time(int(hh), int(mm)))
                    fecha_hora_partido = timezone.make_aware(fecha_hora_partido)
                except (ValueError, AttributeError):
                    fecha_hora_partido = datetime.datetime.combine(fecha_jornada, datetime.time(12, 0))
                    fecha_hora_partido = timezone.make_aware(fecha_hora_partido)

                # Determinar campo evitando conflictos cross-temporada
                campo = None
                # Si la categoría tiene campos_permitidos, restringir a esos
                campos_disponibles = todas_campos
                if self.categoria.campos_permitidos.exists():
                    ids_permitidos = set(self.categoria.campos_permitidos.values_list("pk", flat=True))
                    campos_disponibles = [c for c in todas_campos if c.id in ids_permitidos]

                # Priorizar campo_rancheria del local si está libre y disponible
                if local.campo_rancheria_id:
                    rc = local.campo_rancheria
                    if rc in campos_disponibles and (fecha_hora_partido, rc.id) not in ocupados_externos and (fecha_hora_partido, rc.id) not in nuevos_ocupados:
                        campo = rc
                # Si no hay ranchería o está ocupada, elegir mejor campo libre de los disponibles
                if not campo:
                    libres = [c for c in campos_disponibles
                              if (c.es_rancheria and local.campo_rancheria_id == c.id) or not c.es_rancheria]
                    libres = [c for c in libres
                              if (fecha_hora_partido, c.id) not in ocupados_externos
                              and (fecha_hora_partido, c.id) not in nuevos_ocupados]
                    if libres:
                        if len(libres) == 1:
                            campo = libres[0]
                        else:
                            best_campo = None
                            best_score = float("inf")
                            for c in libres:
                                score = max(team_uso_campo[local.id][c.id], team_uso_campo[visit.id][c.id])
                                if score < best_score:
                                    best_score = score
                                    best_campo = c
                                elif score == best_score:
                                    if uso_campos_jornada[c.id] < uso_campos_jornada[best_campo.id]:
                                        best_campo = c
                            campo = best_campo
                if campo:
                    team_uso_campo[local.id][campo.id] += 1
                    team_uso_campo[visit.id][campo.id] += 1
                    uso_campos_jornada[campo.id] += 1

                Partido.objects.create(
                    temporada=self, jornada=jornada,
                    equipo_local=local, equipo_visitante=visit,
                    campo=campo, fecha_hora=fecha_hora_partido, estado="PEND",
                    grupo=grupo_letra,
                )
                nuevos_ocupados.add((fecha_hora_partido, campo.id if campo else None))
            idx += 1
        return idx

    def _proxima_fecha_juego(self, fecha=None):
        """Próximo día de juego (>= max(fecha, hoy)) según los días de juego de la categoría"""
        import datetime
        from django.utils import timezone
        mapa_dias = {"LUN": 0, "MAR": 1, "MIE": 2, "JUE": 3, "VIE": 4, "SAB": 5, "DOM": 6}
        hoy = timezone.now().date()
        base = max(fecha, hoy) if fecha else hoy
        dias_juego = self.categoria.dias_juego or []
        dias_validos = sorted([mapa_dias[d] for d in dias_juego if d in mapa_dias])
        if not dias_validos:
            return base
        for i in range(8):
            d = base + datetime.timedelta(days=i)
            if d.weekday() in dias_validos:
                return d
        return base

    def generar_rol(self, jornada_inicial=1):
        """Genera TODAS las jornadas y partidos según tipo_rol y vueltas.

        jornada_inicial: umbral para las fechas cuando la temporada ya inició en una
        fecha pasada. Las jornadas anteriores se generan con fechas pasadas (desde
        fecha_inicio) para que el usuario capture cédulas/goles/castigos; desde
        jornada_inicial en adelante se programan desde el próximo día de juego real.
        Con jornada_inicial=1 todo se programa desde fecha_inicio (o desde hoy si ya pasó).
        """
        import datetime
        from .models import HorarioFijoEquipo
        # Limpiar jornadas y partidos previos para evitar duplicados
        Partido.objects.filter(temporada=self).delete()
        Jornada.objects.filter(temporada=self).delete()
        todas_campos = list(Campo.objects.filter(activo=True).order_by("es_rancheria"))
        dias_juego = self.categoria.dias_juego or []
        horarios = self.categoria.horarios or []
        fecha_base = self.fecha_inicio
        fecha_base_futura = self._proxima_fecha_juego(fecha_base)
        horarios_fijos = {
            hf.equipo_id: hf.horario
            for hf in HorarioFijoEquipo.objects.filter(temporada=self)
        }

        if self.tipo_rol == "GRUPOS" and self.num_grupos >= 2:
            grupos = self.grupos_asignados()
            # Generar fixtures de cada grupo con su letra
            all_fixtures = []  # (grupo_letra, fixture_rounds)
            for grupo_letra in sorted(grupos.keys()):
                equipos = grupos[grupo_letra]
                if len(equipos) < 2:
                    continue
                for vuelta in range(self.vueltas):
                    fixture = self._generar_fixture_round_robin(equipos)
                    if vuelta % 2 == 1:
                        fixture = [[(v, l) for l, v in ronda] for ronda in fixture]
                    # Convertir a 3-tuplas (local, visit, grupo_letra)
                    fixture_con_grupo = []
                    for ronda in fixture:
                        fixture_con_grupo.append([(l, v, grupo_letra) for l, v in ronda])
                    all_fixtures.append(fixture_con_grupo)
            # Intercalar rondas de todos los grupos en jornadas compartidas
            max_rounds = max(len(f) for f in all_fixtures) if all_fixtures else 0
            combined_fixture = []
            for r in range(max_rounds):
                ronda_combinada = []
                for f in all_fixtures:
                    if r < len(f):
                        ronda_combinada.extend(f[r])
                combined_fixture.append(ronda_combinada)
            idx = self._crear_partidos_desde_fixture(
                combined_fixture, horarios_fijos, todas_campos,
                fecha_base, dias_juego, horarios, idx_start=1,
                jornada_inicial=jornada_inicial,
                fecha_base_futura=fecha_base_futura,
            )
        else:
            equipos = self.equipos_habilitados()
            idx = 1
            for vuelta in range(self.vueltas):
                fixture = self._generar_fixture_round_robin(equipos)
                if vuelta % 2 == 1:
                    fixture = [[(v, l) for l, v in ronda] for ronda in fixture]
                idx = self._crear_partidos_desde_fixture(
                    fixture, horarios_fijos, todas_campos,
                    fecha_base, dias_juego, horarios, idx,
                    jornada_inicial=jornada_inicial,
                    fecha_base_futura=fecha_base_futura,
                )

        self.actualizar_fecha_fin()
        self._asignar_arbitros_temporada()

    def _pairings_robin_una_vuelta(self, equipos_ids):
        """Devuelve la lista de enfrentamientos (local_id, visit_id) de una vuelta
        round-robin (sin repetir parejas). Retorna también una variante invertida
        para alternar la localía en la segunda vuelta."""
        equipos = list(equipos_ids)
        n = len(equipos)
        if n % 2 != 0:
            equipos.append(None)
            n = len(equipos)
        parejas_ida = []
        for ronda in range(n - 1):
            for i in range(n // 2):
                a, b = equipos[i], equipos[n - 1 - i]
                if a and b:
                    parejas_ida.append((a, b))
            equipos.insert(1, equipos.pop())
        return parejas_ida

    def _equipos_para_rol(self):
        """Equipos que participan en el rol (grupos si aplica, si no todos los habilitados)."""
        if self.tipo_rol == "GRUPOS" and self.num_grupos >= 2:
            grupos = self.grupos_asignados()
            return {gl: [eq.id for eq in eqs if eq] for gl, eqs in grupos.items()}
        return {"": [eq.id for eq in self.equipos_habilitados()]}

    def partidos_por_jornada(self):
        """Cantidad de partidos esperados por jornada según el tipo de rol.

        Incluye a los equipos marcados como abandono: siguen activos en la categoría,
        se les programa su partido en el rol y al marcarlo FIN pierden por default.
        Debe coincidir con lo que genera generar_rol / generar_rol_respaldando_pasadas."""
        equipos = self._equipos_para_rol()
        if self.tipo_rol == "GRUPOS" and self.num_grupos >= 2:
            total = 0
            for ids in equipos.values():
                total += len(ids) // 2
            return max(total, 1)
        ids = equipos.get("", [])
        return max(len(ids) // 2, 1)

    def equipo_abandono_id(self, equipo_id):
        """True si el equipo (por id) abandonó la temporada."""
        return AbandonoTemporada.objects.filter(
            temporada=self, equipo_id=equipo_id
        ).exists()

    def generar_rol_respaldando_pasadas(self, jornada_inicial=1):
        """Genera el rol de las jornadas FUTURAS (>= jornada_inicial) teniendo en cuenta
        los partidos ya registrados a mano en las jornadas pasadas (< jornada_inicial).

        Los partidos pasados (creados manualmente con el wizard de temporada iniciada)
        ya existen en BD con sus jornadas correspondientes. Esta función sólo crea las
        jornadas que faltan y sus enfrentamientos, evitando repetir parejas ya jugadas
        y evitando choques de campo/hora con otras categorías.
        """
        from itertools import cycle
        import datetime as _dt
        from django.utils import timezone
        from .models import Campo, HorarioFijoEquipo

        todas_campos = list(Campo.objects.filter(activo=True))
        dias_juego = self.categoria.dias_juego or []
        horarios = self.categoria.horarios or []
        if not horarios:
            horarios = ["12:00"]
        horarios_fijos = {
            hf.equipo_id: hf.horario
            for hf in HorarioFijoEquipo.objects.filter(temporada=self)
        }
        mapa_dias = {"LUN": 0, "MAR": 1, "MIE": 2, "JUE": 3, "VIE": 4, "SAB": 5, "DOM": 6}

        # --- Cuántas veces se ha enfrentado cada pareja (par no ordenado) ---
        # Si una vuelta entera ya fue jugada, las siguientes vueltas repiten parejas:
        # solo se descartan las apariciones ya consumidas, no la pareja por completo.
        from collections import Counter
        partidos_existentes = Partido.objects.filter(temporada=self)
        veces_jugadas = Counter()
        for a, b in partidos_existentes.values_list("equipo_local_id", "equipo_visitante_id"):
            if a and b:
                veces_jugadas[frozenset((a, b))] += 1
        equipos_por_grupo = self._equipos_para_rol()

        # --- Construir las rondas de jornadas futuras (cada ronda = apareamiento válido) ---
        jornadas_futuras = []

        def _base_vuelta_por_grupo(eqs_ids):
            """Si ya se jugó al menos una vuelta completa, replica su ORDEN real:
            las siguientes vueltas repiten los enfrentamientos de la primera vuelta
            (alternando localía) en el MISMO orden por jornada que se registró,
            en lugar de reordenarlos con el algoritmo."""
            grupo = set(eqs_ids)
            base = []
            vistos = set()
            for p in partidos_existentes.order_by("jornada__numero", "id"):
                a, b = p.equipo_local_id, p.equipo_visitante_id
                if not a or not b or a not in grupo or b not in grupo:
                    continue
                fs = frozenset((a, b))
                if fs in vistos:
                    continue
                vistos.add(fs)
                base.append((a, b))
            todos = set(frozenset((l, v)) for l, v in
                        self._pairings_robin_una_vuelta(eqs_ids))
            if vistos != todos:
                return None, 0
            minimo = min(veces_jugadas.get(fs, 0) for fs in todos)
            return base, minimo

        def _generar_apareamientos_por_vueltas(eqs_ids, grupo_letra):
            """Retorna las parejas (local_id, visit_id) de las vueltas que aún faltan.
            Si la temporada ya cubrió vuelta(s) completas, las vueltas restantes copian
            el orden real de la primera vuelta (localía alternada). En caso parcial usa
            las parejas del algoritmo consumiendo las apariciones ya jugadas."""
            base, jugadas = _base_vuelta_por_grupo(eqs_ids)
            if base and jugadas < self.vueltas:
                total = []
                for v in range(jugadas, self.vueltas):
                    for l, vv in base:
                        if v % 2 == 1:
                            total.append((vv, l, grupo_letra))
                        else:
                            total.append((l, vv, grupo_letra))
                return total
            parejas_ida = self._pairings_robin_una_vuelta(eqs_ids)
            total = []
            restantes = dict(veces_jugadas)
            for vuelta in range(self.vueltas):
                vuelta_pares = list(parejas_ida)
                if vuelta % 2 == 1:
                    vuelta_pares = [(v, l) for l, v in vuelta_pares]
                for l, v in vuelta_pares:
                    fs = frozenset((l, v))
                    if restantes.get(fs, 0) > 0:
                        restantes[fs] -= 1
                        continue
                    total.append((l, v, grupo_letra))
            return total

        def _asignar_jornadas(parejas):
            """Greedy: arma rondas respetando que cada equipo juegue una vez por ronda,
            reiniciando el barrido tras cada emparejamiento para empaquetar rondas
            completas (evita jornadas cortas por una sola pasada)."""
            rondas = []
            disponibles = list(parejas)
            while disponibles:
                ronda = []
                usados = set()
                avanzado = True
                while avanzado:
                    avanzado = False
                    i = 0
                    while i < len(disponibles):
                        l, v, gl = disponibles[i]
                        if l not in usados and v not in usados:
                            ronda.append(disponibles.pop(i))
                            usados.add(l)
                            usados.add(v)
                            avanzado = True
                        else:
                            i += 1
                if not ronda:
                    break
                rondas.append(ronda)
            return rondas

        if self.tipo_rol == "GRUPOS" and self.num_grupos >= 2:
            # Cada grupo acomoda sus parejas en rondas y luego se intercalan entre grupos.
            rondas_por_grupo = {}
            for gl, eqs_ids in equipos_por_grupo.items():
                parejas = _generar_apareamientos_por_vueltas(eqs_ids, gl)
                rondas_por_grupo[gl] = _asignar_jornadas(parejas) or [[]]
            num_rounds = max(len(r) for r in rondas_por_grupo.values())
            for r in range(num_rounds):
                ronda = []
                for gl in sorted(rondas_por_grupo.keys()):
                    if r < len(rondas_por_grupo[gl]):
                        ronda.extend(rondas_por_grupo[gl][r])
                if ronda:
                    jornadas_futuras.append(ronda)
        else:
            eqs_ids = equipos_por_grupo[""]
            parejas = _generar_apareamientos_por_vueltas(eqs_ids, "")
            jornadas_futuras = _asignar_jornadas(parejas)

        # --- Crear jornadas futuras y asignar campo/hora evitando choques ---
        # El cursor arranca el día posterior a la última jornada ya registrada
        # (no desde hoy), para no repetir la fecha de las jornadas pasadas.
        ultima_pasada = partidos_existentes.order_by("-fecha_hora").first()
        base_fecha = (
            (ultima_pasada.fecha_hora.date() + _dt.timedelta(days=1))
            if ultima_pasada and ultima_pasada.fecha_hora
            else self.fecha_inicio
        )
        cursor_fecha = self._proxima_fecha_juego(base_fecha)
        # ocupados cross-temporada (otras temporadas y categorías)
        ocupados_externos = set(
            Partido.objects.filter(estado__in=["PEND", "SUSP"])
            .exclude(temporada=self)
            .values_list("fecha_hora", "campo_id")
        )
        nuevos_ocupados = set()
        team_uso_campo = {e.id: {c.id: 0 for c in todas_campos}
                          for e in self.equipos_habilitados()}

        idx = jornada_inicial
        # Ya pueden existir jornadas pasadas creadas manualmente; evitamos la número prevista
        existentes_numeros = set(self.jornadas.values_list("numero", flat=True))
        for partidos_ronda in jornadas_futuras:
            # avanzar a día válido
            fecha_jornada = None
            dias_validos = sorted([mapa_dias[d] for d in dias_juego if d in mapa_dias])
            if dias_validos:
                cursor = cursor_fecha
                for i in range(20):
                    d = cursor + _dt.timedelta(days=i)
                    if d.weekday() in dias_validos:
                        fecha_jornada = d
                        break
                if fecha_jornada:
                    cursor_fecha = fecha_jornada + _dt.timedelta(days=1)
            if not fecha_jornada:
                fecha_jornada = cursor_fecha
                cursor_fecha = cursor_fecha + _dt.timedelta(days=7)
            # elegir numero de jornada libre (puede que las pasadas no sean 1..N-1 contiguas)
            while idx in existentes_numeros:
                idx += 1
            jornada = Jornada.objects.create(
                temporada=self, numero=idx, nombre=f"Jornada {idx}"
            )
            horarios_cycle = cycle(horarios)
            for item in partidos_ronda:
                if len(item) == 3:
                    local_id, visit_id, grupo_letra = item
                else:
                    local_id, visit_id = item
                    grupo_letra = ""
                hora_local = horarios_fijos.get(local_id) or horarios_fijos.get(visit_id)
                if not hora_local:
                    hora_local = next(horarios_cycle)
                fecha_hora = None
                try:
                    hh, mm = hora_local.split(":")
                    fecha_hora = _dt.datetime.combine(fecha_jornada, _dt.time(int(hh), int(mm)))
                    fecha_hora = timezone.make_aware(fecha_hora)
                except (ValueError, AttributeError):
                    fecha_hora = _dt.datetime.combine(fecha_jornada, _dt.time(12, 0))
                    fecha_hora = timezone.make_aware(fecha_hora)
                local = Equipo.objects.get(pk=local_id)
                visit = Equipo.objects.get(pk=visit_id)
                campo = self._elegir_campo_libre(
                    local, visit, fecha_hora, todas_campos,
                    ocupados_externos, nuevos_ocupados, team_uso_campo,
                )
                Partido.objects.create(
                    temporada=self, jornada=jornada,
                    equipo_local=local, equipo_visitante=visit,
                    campo=campo, fecha_hora=fecha_hora, estado="PEND",
                    grupo=grupo_letra,
                )
                if campo:
                    nuevos_ocupados.add((fecha_hora, campo.id))
                    team_uso_campo[local_id][campo.id] += 1
                    team_uso_campo[visit_id][campo.id] += 1
            idx += 1

        self.actualizar_fecha_fin()
        self._asignar_arbitros_temporada()

    def _elegir_campo_libre(self, local, visit, fecha_hora, todas_campos,
                            ocupados_externos, nuevos_ocupados, team_uso_campo):
        from .models import Campo
        campos_disponibles = todas_campos
        if self.categoria.campos_permitidos.exists():
            ids_permitidos = set(self.categoria.campos_permitidos.values_list("pk", flat=True))
            campos_disponibles = [c for c in todas_campos if c.id in ids_permitidos]
        if local.campo_rancheria_id:
            rc = local.campo_rancheria
            if rc in campos_disponibles and (fecha_hora, rc.id) not in ocupados_externos \
                    and (fecha_hora, rc.id) not in nuevos_ocupados:
                return rc
        # Rancherías solo disponibles para el equipo dueño; las demás se excluyen
        libres = [c for c in campos_disponibles
                  if (fecha_hora, c.id) not in ocupados_externos
                  and (fecha_hora, c.id) not in nuevos_ocupados
                  and (not c.es_rancheria or local.campo_rancheria_id == c.id)]
        if not libres:
            return None
        best = min(libres, key=lambda c: (
            max(team_uso_campo[local.id][c.id], team_uso_campo[visit.id][c.id]),
            c.id,
        ))
        return best

    def calcular_fecha_fin_estimada(self):
        """Estima la fecha de fin basada en equipos, vueltas y días de juego"""
        import datetime
        from collections import defaultdict
        dias_juego = self.categoria.dias_juego or []
        if not dias_juego:
            return self.fecha_inicio
        mapa_dias = {"LUN": 0, "MAR": 1, "MIE": 2, "JUE": 3, "VIE": 4, "SAB": 5, "DOM": 6}
        dias_validos = sorted([mapa_dias[d] for d in dias_juego if d in mapa_dias])
        if not dias_validos:
            return self.fecha_inicio
        total_jornadas = 0
        if self.tipo_rol == "GRUPOS" and self.num_grupos >= 2:
            grupos = self.grupos_asignados()
            for g, eqs in grupos.items():
                n = len(eqs)
                if n >= 2:
                    total_jornadas += (n - 1) * self.vueltas
        else:
            eqs = self.equipos_habilitados()
            n = len(eqs)
            if n >= 2:
                total_jornadas = (n - 1) * self.vueltas
        if total_jornadas == 0:
            return self.fecha_inicio
        # Calcular cuántos días reales se necesitan
        fecha_base = self.fecha_inicio
        semanas_necesarias = (total_jornadas - 1) // len(dias_validos)
        # La última jornada cae en el día válido correspondiente dentro de la última semana
        ultimo_dia_idx = (total_jornadas - 1) % len(dias_validos)
        fecha_est = fecha_base + datetime.timedelta(weeks=semanas_necesarias)
        dia_sem = fecha_est.weekday()
        for d in dias_validos:
            if d >= dia_sem:
                dias_avance = d - dia_sem
                break
        else:
            dias_avance = (7 - dia_sem) + dias_validos[0]
        fecha_est += datetime.timedelta(days=dias_avance)
        # Avanzar al día válido correcto dentro de la semana
        dia_objetivo = dias_validos[ultimo_dia_idx]
        dia_act = fecha_est.weekday()
        diff = (dia_objetivo - dia_act) % 7
        fecha_est += datetime.timedelta(days=diff)
        return fecha_est

    def calcular_tabla(self, jornada_numero=None, incluir_liguilla=False, limit=None, equipos_ids=None):
        """Tabla de posiciones con todos los criterios de desempate de la temporada.
        - jornada_numero: si se especifica, solo considera partidos hasta esa jornada
        - incluir_liguilla: si True incluye partidos de liguilla
        - limit: si se especifica, devuelve solo los primeros N
        - equipos_ids: si se especifica, solo considera partidos entre estos equipos
        """
        partidos = Partido.objects.filter(temporada=self, estado="FIN")
        if jornada_numero is not None:
            partidos = partidos.filter(jornada__numero__lte=jornada_numero)
        if not incluir_liguilla:
            partidos = partidos.filter(es_liguilla=False)
        if equipos_ids:
            partidos = partidos.filter(
                equipo_local_id__in=equipos_ids,
                equipo_visitante_id__in=equipos_ids,
            )
        equipos = {}
        for p in partidos.select_related("equipo_local", "equipo_visitante"):
            for eq_id, gf, gc, es_local in [
                (p.equipo_local_id, p.goles_local, p.goles_visitante, True),
                (p.equipo_visitante_id, p.goles_visitante, p.goles_local, False),
            ]:
                if eq_id not in equipos:
                    eq = p.equipo_local if p.equipo_local_id == eq_id else p.equipo_visitante
                    equipos[eq_id] = {
                        "equipo": eq,
                        "nombre": str(eq),
                        "pj": 0, "pg": 0, "pe": 0, "pp": 0,
                        "gf": 0, "gc": 0, "gf_visit": 0, "pts": 0,
                    }
                else:
                    eq = equipos[eq_id]["equipo"]
                d = equipos[eq_id]
                d["pj"] += 1
                d["gf"] += gf
                d["gc"] += gc
                if not es_local:
                    d["gf_visit"] += gf
                if gf > gc:
                    d["pg"] += 1; d["pts"] += 3
                elif gf == gc:
                    d["pe"] += 1; d["pts"] += 1
                else:
                    d["pp"] += 1
                # Penalización por derrota por default (mora/abandono/alineación indebida)
                if self.puntos_default and p.pierde_por_default(eq):
                    d["pts"] -= self.puntos_default

        def _sort_key(x):
            keys = [x["pts"], x["gf"] - x["gc"], x["gf"]]
            if self.gol_visitante_desempate:
                keys.append(x["gf_visit"])
            return tuple(keys)

        tabla = sorted(equipos.values(), key=_sort_key, reverse=True)

        for t in tabla:
            t["dif"] = t["gf"] - t["gc"]

        if self.posicion_tabla_desempate and len(tabla) >= 2:
            tabla = self._desempate_directo(tabla)

        for i, t in enumerate(tabla, 1):
            t["pos"] = i

        if limit:
            tabla = tabla[:limit]
        return tabla

    def calcular_tablas_por_grupo(self, jornada_numero=None, incluir_liguilla=False, limit=None):
        grupos = self.grupos_asignados()
        result = []
        for letra in sorted(grupos.keys()):
            eqs = grupos[letra]
            group_ids = [e.id for e in eqs if e is not None]
            tabla = self.calcular_tabla(
                jornada_numero=jornada_numero,
                incluir_liguilla=incluir_liguilla,
                limit=limit,
                equipos_ids=group_ids,
            )
            if tabla:
                result.append((letra, tabla))
        return result

    def _desempate_directo(self, tabla):
        """Re-ordena grupos de equipos empatados según enfrentamiento directo."""
        if len(tabla) < 2:
            return tabla
        grupos = []
        grupo_actual = [tabla[0]]
        firma_actual = (tabla[0]["pts"], tabla[0]["dif"], tabla[0]["gf"])
        for t in tabla[1:]:
            firma = (t["pts"], t["dif"], t["gf"])
            if firma == firma_actual:
                grupo_actual.append(t)
            else:
                if len(grupo_actual) >= 2:
                    grupos.append(self._ordenar_por_directo(grupo_actual))
                else:
                    grupos.append(grupo_actual)
                grupo_actual = [t]
                firma_actual = firma
        if len(grupo_actual) >= 2:
            grupos.append(self._ordenar_por_directo(grupo_actual))
        else:
            grupos.append(grupo_actual)
        resultado = []
        for g in grupos:
            resultado.extend(g)
        return resultado

    def _ordenar_por_directo(self, grupo):
        """Ordena un grupo de equipos empatados por enfrentamiento directo."""
        ids = [t["equipo"].id for t in grupo]
        pts_directo = {t["equipo"].id: 0 for t in grupo}
        gf_directo = {t["equipo"].id: 0 for t in grupo}
        gc_directo = {t["equipo"].id: 0 for t in grupo}
        partidos = Partido.objects.filter(
            temporada=self, estado="FIN", es_liguilla=False,
            equipo_local_id__in=ids, equipo_visitante_id__in=ids,
        )
        for p in partidos:
            if p.equipo_local_id in ids and p.equipo_visitante_id in ids:
                if p.goles_local > p.goles_visitante:
                    pts_directo[p.equipo_local_id] += 3
                elif p.goles_local == p.goles_visitante:
                    pts_directo[p.equipo_local_id] += 1
                    pts_directo[p.equipo_visitante_id] += 1
                else:
                    pts_directo[p.equipo_visitante_id] += 3
                gf_directo[p.equipo_local_id] += p.goles_local
                gf_directo[p.equipo_visitante_id] += p.goles_visitante
                gc_directo[p.equipo_local_id] += p.goles_visitante
                gc_directo[p.equipo_visitante_id] += p.goles_local
        grupo.sort(key=lambda t: (pts_directo[t["equipo"].id], gf_directo[t["equipo"].id] - gc_directo[t["equipo"].id], gf_directo[t["equipo"].id]), reverse=True)
        return grupo

    def _asignar_arbitros_temporada(self):
        """Asigna árbitros activos a todos los partidos de la temporada que no tengan árbitro.
        Distribuye equitativamente: mismo árbitro no se repite en el mismo horario del mismo día,
        y se prefiere mantener el mismo árbitro en el mismo campo durante la misma fecha."""
        from .models import Arbitro
        arbitros = list(Arbitro.objects.filter(activo=True))
        if not arbitros:
            return
        partidos = list(Partido.objects.filter(temporada=self, arbitro__isnull=True).order_by("fecha_hora"))
        if not partidos:
            return
        total_asignaciones = {a.id: Partido.objects.filter(temporada=self, arbitro=a).count() for a in arbitros}
        ocupados = {}
        campo_ref = {}
        for p in partidos:
            if not p.fecha_hora:
                continue
            fecha = p.fecha_hora.date()
            time_key = p.fecha_hora.time().strftime("%H:%M")
            ocupados.setdefault(fecha, {})
            campo_ref.setdefault(fecha, {})
            fa = ocupados[fecha]
            ca = campo_ref[fecha]
            preferred = ca.get(p.campo_id) if p.campo else None
            if preferred and preferred not in fa.get(time_key, set()):
                p.arbitro_id = preferred
                total_asignaciones[preferred] += 1
                fa.setdefault(time_key, set()).add(preferred)
                p.save(update_fields=["arbitro_id"])
                continue
            disponibles = sorted(
                [a for a in arbitros if a.id not in fa.get(time_key, set())],
                key=lambda a: total_asignaciones[a.id]
            )
            if not disponibles:
                continue
            elegido = disponibles[0]
            p.arbitro_id = elegido.id
            total_asignaciones[elegido.id] += 1
            fa.setdefault(time_key, set()).add(elegido.id)
            if p.campo:
                ca[p.campo_id] = elegido.id
            p.save(update_fields=["arbitro_id"])

    def _crear_partido_liguilla(self, jornada, local, visit, todas_campos, idx, num_campos, horarios_cycle, fecha_base, leg=1):
        """Crea un partido de liguilla."""
        from .models import Partido, HorarioFijoEquipo
        import datetime
        horarios_lista = self.categoria.horarios or ["12:00"]
        day_start = timezone.make_aware(datetime.datetime.combine(fecha_base, datetime.time(0, 0)))
        day_end = day_start + datetime.timedelta(days=1)
        ocupados = set(
            Partido.objects.filter(
                fecha_hora__gte=day_start, fecha_hora__lt=day_end
            ).values_list("campo_id", "fecha_hora")
        )
        # Horario fijo del equipo local, luego visitante
        hf = {hf.equipo_id: hf.horario for hf in HorarioFijoEquipo.objects.filter(temporada=self, equipo__in=[local, visit])}
        hora_preferida = hf.get(local.id) or hf.get(visit.id)
        # Construir lista de horarios a probar: preferido primero, luego el resto
        horarios_a_probar = list(horarios_lista)
        if hora_preferida and hora_preferida in horarios_a_probar:
            horarios_a_probar.remove(hora_preferida)
            horarios_a_probar.insert(0, hora_preferida)
        # Generar slots (campo, horario) ordenados, empezando desde la posicion asignada
        # Si local tiene ranchería, usar su campo directamente
        if local and local.campo_rancheria_id:
            campo = local.campo_rancheria
            for h in horarios_a_probar:
                try:
                    hh, mm = h.split(":")
                    dt = timezone.make_aware(datetime.datetime.combine(fecha_base, datetime.time(int(hh), int(mm))))
                except (ValueError, AttributeError):
                    dt = timezone.make_aware(datetime.datetime.combine(fecha_base, datetime.time(12, 0)))
                if (campo.pk, dt) not in ocupados:
                    fecha_hora = dt
                    break
            else:
                try:
                    hh, mm = (hora_preferida or horarios_lista[0]).split(":")
                    fecha_hora = timezone.make_aware(datetime.datetime.combine(fecha_base, datetime.time(int(hh), int(mm))))
                except (ValueError, AttributeError):
                    fecha_hora = timezone.make_aware(datetime.datetime.combine(fecha_base, datetime.time(12, 0)))
        else:
            for di in range(num_campos):
                c = todas_campos[(idx + di) % num_campos] if num_campos > 0 else None
                c_pk = c.pk if c else None
                for h in horarios_a_probar:
                    try:
                        hh, mm = h.split(":")
                        dt = timezone.make_aware(datetime.datetime.combine(fecha_base, datetime.time(int(hh), int(mm))))
                    except (ValueError, AttributeError):
                        dt = timezone.make_aware(datetime.datetime.combine(fecha_base, datetime.time(12, 0)))
                    if (c_pk, dt) not in ocupados:
                        campo = c
                        fecha_hora = dt
                        break
                else:
                    continue
                break
            else:
                # Todos ocupados: usar asignacion original con horario preferido
                campo = todas_campos[idx % num_campos] if num_campos > 0 else None
                try:
                    hh, mm = (hora_preferida or horarios_lista[0]).split(":")
                    fecha_hora = timezone.make_aware(datetime.datetime.combine(fecha_base, datetime.time(int(hh), int(mm))))
                except (ValueError, AttributeError):
                    fecha_hora = timezone.make_aware(datetime.datetime.combine(fecha_base, datetime.time(12, 0)))
        Partido.objects.create(
            temporada=self, jornada=jornada,
            equipo_local=local, equipo_visitante=visit,
            campo=campo, fecha_hora=fecha_hora, estado="PEND",
            es_liguilla=True, liguilla_leg=leg if leg > 1 else None,
        )

    def _nombre_ronda(self, num_equipos_ronda, total_equipos_iniciales):
        """Nombre descriptivo de la ronda segun cuantos equipos quedan."""
        if num_equipos_ronda == 2:
            return "Final"
        if num_equipos_ronda == 4:
            return "Semifinales"
        if num_equipos_ronda <= 8:
            return "Cuartos de Final"
        if num_equipos_ronda <= 16:
            return "Octavos de Final"
        return f"Ronda {total_equipos_iniciales // num_equipos_ronda}"

    def generar_siguiente_ronda(self):
        """Genera la siguiente ronda de liguilla usando los ganadores de la ronda anterior.
        Si no hay rondas previas, genera la primera desde la tabla de posiciones."""
        from .models import Partido, Jornada
        from django.db.models import Max
        import datetime
        if self.tipo_competencia != "LIGUILLA":
            raise ValueError("Esta temporada no es de tipo Liguilla.")

        clasificados = self.num_clasificados
        equipos = self.equipos_habilitados()
        if len(equipos) < clasificados:
            clasificados = len(equipos)
        if clasificados < 2:
            raise ValueError("No hay suficientes equipos clasificados.")

        liguilla_jornadas = list(Jornada.objects.filter(
            temporada=self, partidos__es_liguilla=True
        ).distinct().order_by("numero"))

        uso_ida_vuelta = self.ida_vuelta

        if not liguilla_jornadas:
            # Primera ronda: desde la tabla de posiciones
            if self.clasificacion_por_grupos and self.tipo_rol == "GRUPOS":
                equipos_ronda = []
                grupos = self.grupos_asignados()
                por_grupo = max(1, clasificados // max(len(grupos), 1))
                grupos_ordenados = sorted(grupos.items())
                clasificados_por_grupo = {}
                for letra, eqs in grupos_ordenados:
                    group_ids = [e.id for e in eqs if e is not None]
                    tabla_grupo = self.calcular_tabla(incluir_liguilla=False, equipos_ids=group_ids)
                    clasificados_por_grupo[letra] = [(t["equipo"], pos) for pos, t in enumerate(tabla_grupo[:por_grupo], 1)]
                    equipos_ronda.extend(t["equipo"] for t in tabla_grupo[:por_grupo])
            else:
                tabla = self.calcular_tabla(incluir_liguilla=False)
                equipos_ronda = [t["equipo"] for t in tabla[:clasificados]]
        else:
            # Verificar que todos los partidos de la ultima ronda esten FIN
            ult_jornada = liguilla_jornadas[-1]
            partidos_ult = Partido.objects.filter(jornada=ult_jornada, es_liguilla=True)
            no_fin = partidos_ult.exclude(estado="FIN")
            if no_fin.exists():
                nom = ult_jornada.nombre
                raise ValueError(
                    f"Hay {no_fin.count()} partido(s) pendiente(s) en '{nom}'. "
                    f"Finaliza todos antes de avanzar."
                )
            # Obtener ganadores de la ronda anterior
            equipos_ronda = self._ganadores_ronda(partidos_ult)
            if len(equipos_ronda) <= 1:
                raise ValueError("La liguilla ya ha finalizado. No hay más rondas que generar.")
            # Si la ronda anterior fue ida/vuelta, la final usa su propia config
            if len(equipos_ronda) == 2 and clasificados > 2:
                # Verificar si es la final
                ult_nombre = ult_jornada.nombre
                # Si la ronda anterior tenia 2 equipos (o 2 equipos/2=1 partido por vuelta),
                # significa que ya pasamos semis y estamos en final
                num_partidos_ult = partidos_ult.count()
                # ida_vuelta duplica los partidos: 2 jugadores = 2 partidos (ida/vuelta)
                if (self.final_ida_vuelta and not self.ida_vuelta) or \
                   (self.final_ida_vuelta and self.ida_vuelta):
                    # La final usa final_ida_vuelta en vez de ida_vuelta general
                    pass  # se decide abajo
                uso_ida_vuelta = self.final_ida_vuelta if clasificados > 2 else self.ida_vuelta

        total_inicial = clasificados
        n = len(equipos_ronda)
        dias_juego = self.categoria.dias_juego or []
        horarios = self.categoria.horarios or []
        mapa_dias = {"LUN": 0, "MAR": 1, "MIE": 2, "JUE": 3, "VIE": 4, "SAB": 5, "DOM": 6}
        dias_validos = sorted([mapa_dias[d] for d in dias_juego if d in mapa_dias])
        ultima_jornada = Jornada.objects.filter(temporada=self).aggregate(m=Max("numero"))["m"] or 0
        # Fecha base: fin de temporada regular, o ultimo partido, o hoy como fallback
        fecha_base = self.fecha_fin or datetime.date.today()
        ultimo_regular = Partido.objects.filter(temporada=self, es_liguilla=False).order_by("-fecha_hora").first()
        if ultimo_regular and ultimo_regular.fecha_hora:
            fecha_base = max(fecha_base, ultimo_regular.fecha_hora.date())
        # Si ya hay rondas de liguilla, la siguiente ronda empieza despues de la ultima
        if liguilla_jornadas:
            ultimo_liguilla = Partido.objects.filter(
                temporada=self, es_liguilla=True
            ).order_by("-fecha_hora").first()
            if ultimo_liguilla and ultimo_liguilla.fecha_hora:
                fecha_base = max(fecha_base, ultimo_liguilla.fecha_hora.date())
        if dias_validos:
            cursor = fecha_base + datetime.timedelta(weeks=1)
            dia_semana = cursor.weekday()
            for d in dias_validos:
                if d >= dia_semana:
                    dias_avance = d - dia_semana
                    break
            else:
                dias_avance = (7 - dia_semana) + dias_validos[0]
            fecha_base = cursor + datetime.timedelta(days=dias_avance)
        from itertools import cycle
        horarios_cycle = cycle(horarios) if horarios else cycle(["12:00"])
        todas_campos = list(Campo.objects.filter(activo=True).order_by("es_rancheria"))
        num_campos = len(todas_campos)

        ultima_jornada += 1
        nombre_ronda = self._nombre_ronda(n, total_inicial)
        jornada = Jornada.objects.create(
            temporada=self, numero=ultima_jornada,
            nombre=nombre_ronda
        )
        # Pairing: 1st vs last, 2nd vs second-last, etc.
        # El mejor posicionado (mas puntos en tabla general) es local en la vuelta
        if self.clasificacion_por_grupos and self.tipo_rol == "GRUPOS" and not liguilla_jornadas:
            # Emparejamiento cruzado entre grupos: A1 vs B2, B1 vs A2, C1 vs D2, D1 vs C2, etc.
            grupos_lista = sorted(clasificados_por_grupo.items())
            pares = []
            for idx in range(0, len(grupos_lista), 2):
                g1 = grupos_lista[idx]
                g2 = grupos_lista[idx + 1] if idx + 1 < len(grupos_lista) else None
                if g2 is None:
                    pares.append((g1[1][0][0], g1[1][1][0]))
                else:
                    pares.append((g1[1][0][0], g2[1][1][0]))  # A1 vs B2
                    pares.append((g2[1][0][0], g1[1][1][0]))  # B1 vs A2
            for i, (local, visit) in enumerate(pares):
                if uso_ida_vuelta:
                    self._crear_partido_liguilla(jornada, visit, local, todas_campos, i, num_campos, horarios_cycle, fecha_base)
                    self._crear_partido_liguilla(jornada, local, visit, todas_campos, i, num_campos, horarios_cycle, fecha_base + datetime.timedelta(weeks=1), leg=2)
                else:
                    self._crear_partido_liguilla(jornada, local, visit, todas_campos, i, num_campos, horarios_cycle, fecha_base)
        else:
            for i in range(n // 2):
                mejor = equipos_ronda[i]
                peor = equipos_ronda[-(i + 1)]
                if uso_ida_vuelta:
                    # Ida: peor posicionado es local; ida del mejor como visitante
                    self._crear_partido_liguilla(jornada, peor, mejor, todas_campos, i, num_campos, horarios_cycle, fecha_base)
                    # Vuelta: mejor posicionado es local
                    self._crear_partido_liguilla(jornada, mejor, peor, todas_campos, i, num_campos, horarios_cycle, fecha_base + datetime.timedelta(weeks=1), leg=2)
                else:
                    # Un solo partido: mejor posicionado es local
                    self._crear_partido_liguilla(jornada, mejor, peor, todas_campos, i, num_campos, horarios_cycle, fecha_base)

        self._asignar_arbitros_temporada()
        self.actualizar_fecha_fin()

    def _ganadores_ronda(self, partidos_qs):
        """Retorna lista de equipos que ganaron sus series en una ronda.
        Para ida/vuelta, suma goles globales; si hay empate usa criterios."""
        partidos = list(partidos_qs)
        if not partidos:
            return []
        # Agrupar por pareja de equipos (ida/vuelta)
        parejas = {}
        for p in partidos:
            key = tuple(sorted([p.equipo_local_id, p.equipo_visitante_id]))
            parejas.setdefault(key, []).append(p)
        ganadores = []
        for key, pjs in parejas.items():
            if len(pjs) == 1:
                p = pjs[0]
                if p.goles_local > p.goles_visitante:
                    ganadores.append(p.equipo_local)
                elif p.goles_visitante > p.goles_local:
                    ganadores.append(p.equipo_visitante)
                else:
                    ganadores.append(p.equipo_local)  # empate -> local
            else:
                # Ida y vuelta: sumar global por equipo (NO por local/visit)
                equipo_a = pjs[0].equipo_local
                equipo_b = pjs[0].equipo_visitante
                gol_a, gol_b = 0, 0
                for p in pjs:
                    if p.equipo_local_id == equipo_a.id:
                        gol_a += p.goles_local
                        gol_b += p.goles_visitante
                    else:
                        gol_a += p.goles_visitante
                        gol_b += p.goles_local
                if gol_a > gol_b:
                    ganadores.append(equipo_a)
                elif gol_b > gol_a:
                    ganadores.append(equipo_b)
                else:
                    # Empate global: aplicar criterio de desempate configurado
                    if self.criterio_liguilla == "gol_visitante":
                        gv_a = sum(p.goles_visitante for p in pjs if p.equipo_local_id == equipo_b.id)
                        gv_b = sum(p.goles_visitante for p in pjs if p.equipo_local_id == equipo_a.id)
                        if gv_b > gv_a:
                            ganadores.append(equipo_b)
                        elif gv_a > gv_b:
                            ganadores.append(equipo_a)
                        else:
                            ganadores.append(self._mejor_posicionado([equipo_a, equipo_b]))
                    elif self.criterio_liguilla == "posicion_tabla":
                        ganadores.append(self._mejor_posicionado([equipo_a, equipo_b]))
                    else:
                        ganadores.append(equipo_a)  # sin criterio -> local de ida
        return ganadores

    def _mejor_posicionado(self, equipos):
        """De una lista de equipos, retorna el mejor posicionado en la tabla general."""
        tabla = self.calcular_tabla(incluir_liguilla=False)
        for t in tabla:
            e = t["equipo"]
            if e in equipos:
                return e
        return equipos[0] if equipos else None

    @property
    def puede_iniciar_liguilla(self):
        return not Partido.objects.filter(
            temporada=self, es_liguilla=False
        ).exclude(estado="FIN").exists()

    def estado_liguilla(self):
        """Retorna el estado actual de la liguilla:
        - 'no_iniciada': no hay jornadas de liguilla
        - 'en_curso': hay jornadas con partidos pendientes
        - 'lista_avanzar': todos los partidos de la ultima ronda estan FIN, se puede avanzar
        - 'completada': todas las rondas jugadas, hay un campeon
        """
        from .models import Partido, Jornada
        if self.tipo_competencia != "LIGUILLA":
            return "no_aplica"
        liguilla_jornadas = list(Jornada.objects.filter(
            temporada=self, partidos__es_liguilla=True
        ).distinct().order_by("numero"))
        if not liguilla_jornadas:
            return "no_iniciada"
        ult_jornada = liguilla_jornadas[-1]
        partidos_ult = Partido.objects.filter(jornada=ult_jornada, es_liguilla=True)
        no_fin = partidos_ult.exclude(estado="FIN")
        if no_fin.exists():
            return "en_curso"
        # Todos FIN en ultima ronda
        ganadores = self._ganadores_ronda(partidos_ult)
        if len(ganadores) <= 1:
            return "completada"
        return "lista_avanzar"

    def obtener_campeon(self):
        """Retorna el equipo campeon, o None si la liguilla no esta completa."""
        from .models import Partido, Jornada
        estado = self.estado_liguilla()
        if estado != "completada":
            return None
        liguilla_jornadas = list(Jornada.objects.filter(
            temporada=self, partidos__es_liguilla=True
        ).distinct().order_by("numero"))
        ult_jornada = liguilla_jornadas[-1]
        partidos_ult = Partido.objects.filter(jornada=ult_jornada, es_liguilla=True)
        ganadores = self._ganadores_ronda(partidos_ult)
        return ganadores[0] if ganadores else None

    def jornada_actual(self):
        hoy = timezone.now().date()
        partido = self.partidos.filter(
            fecha_hora__date__lte=hoy, jornada__isnull=False
        ).order_by("-jornada__numero").first()
        return partido.jornada.numero if partido and partido.jornada else 0

    def periodo_altas_activo(self, fecha=None, jornada_num=None):
        """Verifica si hay un periodo de altas activo para la fecha/jornada dada"""
        qs = PeriodoAltas.objects.filter(temporada=self, activo=True)
        if not qs.exists():
            return False
        if fecha is None:
            fecha = timezone.now().date()
        if jornada_num is None:
            jornada_num = self.jornada_actual()
        for p in qs:
            if p.tipo == "fechas":
                if fecha and p.fecha_inicio and p.fecha_fin and p.fecha_inicio <= fecha <= p.fecha_fin:
                    return True
            elif p.tipo == "jornadas":
                if jornada_num and p.jornada_inicio and p.jornada_fin and p.jornada_inicio <= jornada_num <= p.jornada_fin:
                    return True
        return False


class AbandonoTemporada(models.Model):
    temporada = models.ForeignKey(
        Temporada, on_delete=models.CASCADE, related_name="abandonos"
    )
    equipo = models.ForeignKey(
        "Equipo", on_delete=models.CASCADE, related_name="abandonos"
    )
    fecha = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "Abandono de Temporada"
        verbose_name_plural = "Abandonos de Temporada"
        unique_together = ["temporada", "equipo"]

    def __str__(self):
        return f"{self.equipo.nombre} abandonó {self.temporada.nombre} el {self.fecha}"


class Grupo(models.Model):
    temporada = models.ForeignKey(
        Temporada, on_delete=models.CASCADE, related_name="grupos"
    )
    equipo = models.ForeignKey(
        "Equipo", on_delete=models.CASCADE, related_name="grupos"
    )
    grupo = models.CharField(max_length=10, verbose_name="Grupo (A, B, C...)")
    orden = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Grupo"
        verbose_name_plural = "Grupos"
        unique_together = ["temporada", "equipo"]
        ordering = ["grupo", "orden"]

    def __str__(self):
        return f"Grupo {self.grupo}: {self.equipo.nombre}"


class Jornada(models.Model):
    ESTADOS = [
        ("ACTIVA", "Activa"),
        ("SUSPENDIDA", "Suspendida"),
    ]
    temporada = models.ForeignKey(
        Temporada, on_delete=models.CASCADE, related_name="jornadas"
    )
    numero = models.IntegerField()
    nombre = models.CharField(max_length=100)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="ACTIVA")
    motivo_suspension = models.TextField(blank=True)
    semanas_suspension = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Jornada"
        verbose_name_plural = "Jornadas"
        ordering = ["temporada", "numero"]
        unique_together = ["temporada", "numero"]

    def __str__(self):
        return f"{self.temporada.nombre} - {self.nombre}"


class PeriodoAltas(models.Model):
    TIPOS = [
        ("fechas", "Por rango de fechas"),
        ("jornadas", "Por rango de jornadas"),
    ]
    temporada = models.ForeignKey(
        Temporada, on_delete=models.CASCADE, related_name="periodos_altas"
    )
    tipo = models.CharField(max_length=10, choices=TIPOS)
    fecha_inicio = models.DateField(blank=True, null=True)
    fecha_fin = models.DateField(blank=True, null=True)
    jornada_inicio = models.IntegerField(blank=True, null=True)
    jornada_fin = models.IntegerField(blank=True, null=True)
    extraordinario = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Período de Altas/Bajas"
        verbose_name_plural = "Períodos de Altas/Bajas"

    def __str__(self):
        if self.tipo == "fechas":
            return f"Altas por fechas: {self.fecha_inicio} - {self.fecha_fin} ({self.temporada})"
        return f"Altas por jornadas: {self.jornada_inicio} - {self.jornada_fin} ({self.temporada})"


class PartidoQuerySet(models.QuerySet):
    def _fetch_all(self):
        try:
            super()._fetch_all()
        except ProgrammingError as e:
            if "does not exist" in str(e) and "recordatorio_30min_enviado" in str(e):
                from django.db import connection
                with connection.cursor() as cur:
                    cur.execute("ALTER TABLE league_partido ADD COLUMN IF NOT EXISTS recordatorio_30min_enviado boolean NOT NULL DEFAULT false")
                super()._fetch_all()
            else:
                raise


class PartidoManager(Manager):
    def get_queryset(self):
        return PartidoQuerySet(self.model, using=self._db)


class Partido(models.Model):
    ESTADOS = [
        ("PEND", "Pendiente"),
        ("SUSP", "Suspendido"),
        ("JUG", "Jugando"),
        ("FIN", "Finalizado"),
    ]
    temporada = models.ForeignKey(
        Temporada, on_delete=models.CASCADE, related_name="partidos",
        null=True, blank=True,
        help_text="Obligatorio para partidos de liga. Déjalo vacío para partidos amistosos."
    )
    jornada = models.ForeignKey(
        "Jornada", on_delete=models.CASCADE, related_name="partidos",
        null=True, blank=True
    )
    equipo_local = models.ForeignKey(
        Equipo, on_delete=models.CASCADE, related_name="partidos_local"
    )
    equipo_visitante = models.ForeignKey(
        Equipo, on_delete=models.CASCADE, related_name="partidos_visitante"
    )
    campo = models.ForeignKey(
        Campo, on_delete=models.SET_NULL, null=True, related_name="partidos"
    )
    arbitro = models.ForeignKey(
        "Arbitro", on_delete=models.SET_NULL, null=True, blank=True, related_name="partidos"
    )
    fecha_hora = models.DateTimeField()
    goles_local = models.IntegerField(default=0)
    goles_visitante = models.IntegerField(default=0)
    estado = models.CharField(max_length=4, choices=ESTADOS, default="PEND")
    es_liguilla = models.BooleanField(default=False, verbose_name="Es partido de liguilla")
    es_amistoso = models.BooleanField(default=False, verbose_name="Es partido amistoso")
    liguilla_leg = models.IntegerField(null=True, blank=True, verbose_name="Partido de liguilla (1=ida, 2=vuelta)")
    observaciones = models.TextField(blank=True, verbose_name="Observaciones")
    default_team = models.CharField(max_length=10, blank=True, null=True, choices=[("local", "Local"), ("visitante", "Visitante")], verbose_name="Local pierde por default (obsoleto)")
    default_visitante = models.BooleanField(default=False, verbose_name="Visitante pierde por default")
    motivo_default = models.TextField(blank=True, verbose_name="Motivo del default")
    grupo = models.CharField(max_length=1, blank=True, verbose_name="Grupo")
    recordatorio_30min_enviado = models.BooleanField(default=False, verbose_name="Recordatorio 30min enviado")
    objects = PartidoManager()

    class Meta:
        verbose_name = "Partido"
        verbose_name_plural = "Partidos"

    def __str__(self):
        return f"{self.equipo_local} vs {self.equipo_visitante}"

    def save(self, *args, **kwargs):
        if self.pk:
            old = Partido.objects.get(pk=self.pk)
        else:
            old = None

        # Auto-finalizar si cambiaron los goles (comportamiento original)
        if old is not None:
            if (old.goles_local != self.goles_local or
                old.goles_visitante != self.goles_visitante):
                self.estado = "FIN"

        # Si el partido se marca como FIN, aplicar walkover por mora/abandono (solo liga)
        # El ganador recibe 1 gol y se libera el CAMPO (el partido no se juega).
        # fecha_hora se conserva: la columna es NOT NULL y la fecha/orden del
        # fixture no debe perderse.
        if self.estado == "FIN" and self.temporada_id:
            local_debe = self.temporada.equipo_debe_partido(self.equipo_local)
            visit_debe = self.temporada.equipo_debe_partido(self.equipo_visitante)
            if local_debe and not visit_debe:
                self.goles_local = 0
                self.goles_visitante = 1
                self.campo = None
            elif visit_debe and not local_debe:
                self.goles_local = 1
                self.goles_visitante = 0
                self.campo = None
            elif local_debe and visit_debe:
                self.goles_local = 0
                self.goles_visitante = 0
                self.campo = None

        # Un partido marcado como default (walkover por baja/alineación) no se juega:
        # liberar el campo para dejar libre ese bloque.
        if (self.default_team == "local" or self.default_visitante) and self.estado == "FIN":
            self.campo = None

        super().save(*args, **kwargs)

        # Auto-finalizar la temporada si este partido completa la liguilla (solo liga)
        if self.estado == "FIN" and self.es_liguilla and self.temporada_id and not self.temporada.finalizada:
            if self.temporada.estado_liguilla() == "completada":
                self.temporada.finalizada = True
                self.temporada.fecha_finalizacion = timezone.now().date()
                self.temporada.save(update_fields=["finalizada", "fecha_finalizacion"])

    def partido_ida(self):
        """Retorna el partido de ida si este es de vuelta, o None."""
        if not self.es_liguilla or self.liguilla_leg != 2:
            return None
        return Partido.objects.filter(
            jornada=self.jornada,
            es_liguilla=True,
            liguilla_leg__isnull=True,
            equipo_local=self.equipo_visitante,
            equipo_visitante=self.equipo_local,
        ).first()

    def pierde_por_default(self, equipo):
        """True si `equipo` perdió (o empató) este partido por default:
        mora, abandono o marcado explícitamente desde cédula (alineación indebida)."""
        if self.estado != "FIN":
            return False
        if equipo == self.equipo_local:
            if self.default_team == "local":
                return True
            if self.temporada_id and self.temporada.equipo_debe_partido(self.equipo_local):
                return self.goles_local <= self.goles_visitante
            return False
        if equipo == self.equipo_visitante:
            if self.default_visitante or self.default_team == "visitante":
                return True
            if self.temporada_id and self.temporada.equipo_debe_partido(self.equipo_visitante):
                return self.goles_visitante <= self.goles_local
            return False
        return False

    @property
    def ganador_walkover(self):
        """Equipo que gana este partido por default (walkover), o None si el partido
        no involucra mora, abandono o alineación indebida. Funciona tanto para
        partidos finalizados (default marcado) como pendientes (equipo en mora/abandono)."""
        if self.estado != "FIN":
            if self.temporada_id:
                if self.temporada.equipo_debe_partido(self.equipo_local):
                    return self.equipo_visitante
                if self.temporada.equipo_debe_partido(self.equipo_visitante):
                    return self.equipo_local
            return None
        if self.default_team == "local":
            return self.equipo_visitante
        if self.default_visitante:
            return self.equipo_local
        if self.temporada_id and self.temporada.equipo_debe_partido(self.equipo_local) \
                and self.goles_local <= self.goles_visitante:
            return self.equipo_visitante
        if self.temporada_id and self.temporada.equipo_debe_partido(self.equipo_visitante) \
                and self.goles_visitante <= self.goles_local:
            return self.equipo_local
        return None

    def agregado_info(self):
        """Retorna dict con marcador global si es vuelta, o None.
        
        El dict contiene:
            total_local, total_visitante: goles sumados de ida+vuelta
            avanza_local: True si avanza el local, False si avanza visitante, None si indefinido
        """
        if not self.es_liguilla or self.liguilla_leg != 2:
            return None
        ida = self.partido_ida()
        if not ida:
            return None
        total_local = ida.goles_visitante + self.goles_local
        total_visit = ida.goles_local + self.goles_visitante
        # Solo determinar ganador si la vuelta esta finalizada
        if self.estado == "FIN":
            if total_local > total_visit:
                avanza_local = True
            elif total_visit > total_local:
                avanza_local = False
            else:
                gv_local = ida.goles_visitante
                gv_visit = self.goles_visitante
                crit = self.temporada.criterio_liguilla
                if crit == "posicion_tabla":
                    ganador = self.temporada._mejor_posicionado(
                        [self.equipo_local, self.equipo_visitante]
                    )
                    avanza_local = ganador == self.equipo_local
                elif crit == "gol_visitante":
                    if gv_local > gv_visit:
                        avanza_local = True
                    elif gv_visit > gv_local:
                        avanza_local = False
                    else:
                        ganador = self.temporada._mejor_posicionado(
                            [self.equipo_local, self.equipo_visitante]
                        )
                        avanza_local = ganador == self.equipo_local
                else:
                    avanza_local = False
        else:
            avanza_local = None
        return {
            "total_local": total_local,
            "total_visitante": total_visit,
            "avanza_local": avanza_local,
        }

    @property
    def es_ida(self):
        """True si es un partido de ida (tiene una vuelta correspondiente)."""
        if not self.es_liguilla or self.liguilla_leg:
            return False
        return Partido.objects.filter(
            jornada=self.jornada,
            es_liguilla=True,
            liguilla_leg=2,
            equipo_local=self.equipo_visitante,
            equipo_visitante=self.equipo_local,
        ).exists()


class Gol(models.Model):
    TIPOS = [
        ("NORMAL", "Normal"),
        ("PENAL", "Penalti"),
        ("TIRO_LIBRE", "Tiro Libre"),
        ("AUTOGOL", "Autogol"),
    ]
    partido = models.ForeignKey(
        Partido, on_delete=models.CASCADE, related_name="goles"
    )
    jugador = models.ForeignKey(
        Jugador, on_delete=models.CASCADE, related_name="goles"
    )
    equipo = models.ForeignKey(
        Equipo, on_delete=models.CASCADE, related_name="goles"
    )
    minuto = models.IntegerField()
    tipo = models.CharField(max_length=10, choices=TIPOS, default="NORMAL")

    class Meta:
        verbose_name = "Gol"
        verbose_name_plural = "Goles"

    def __str__(self):
        return f"{self.jugador} (Gol)"


class Tarjeta(models.Model):
    TIPOS = [
        ("AMARILLA", "Tarjeta Amarilla"),
        ("ROJA", "Tarjeta Roja"),
    ]
    partido = models.ForeignKey(
        Partido, on_delete=models.CASCADE, related_name="tarjetas"
    )
    jugador = models.ForeignKey(
        Jugador, on_delete=models.CASCADE, related_name="tarjetas"
    )
    equipo = models.ForeignKey(
        Equipo, on_delete=models.CASCADE, related_name="tarjetas"
    )
    tipo = models.CharField(max_length=10, choices=TIPOS)
    minuto = models.IntegerField()
    suspension_jornadas = models.IntegerField(default=0, verbose_name="Jornadas de suspensión")

    class Meta:
        verbose_name = "Tarjeta"
        verbose_name_plural = "Tarjetas"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.jugador} ({self.minuto}')"


class MovimientoEquipo(models.Model):
    """Movimiento de un equipo al cerrar una temporada (ascenso/descenso/desaparición).

    Se registra al finalizar la temporada y sirve para:
    - Mover el equipo físicamente de categoría (Equipo.categoria = destino).
    - Restringir el registro de sus jugadores en la siguiente temporada:
      * DESCENSO:  solo pueden jugar en la categoría a la que bajó o una más abajo.
      * DESAPARECE: solo en la categoría donde estaba o la inmediata inferior.
      * ASCENSO:    puede cambiarse a otro equipo solo si es de la categoría a la que
                    ascendió o la inmediata inferior; y solo el 50% de la plantilla
                    (los primeros que se registren en el nuevo equipo).
    """
    TIPOS = [
        ("ASCENSO", "Asciende"),
        ("DESCENSO", "Desciende"),
        ("DESAPARECE", "Desaparece"),
        ("SE_QUEDA", "Se queda"),
    ]
    temporada = models.ForeignKey(
        "Temporada", on_delete=models.CASCADE, related_name="movimientos_equipos"
    )
    equipo = models.ForeignKey(
        "Equipo", on_delete=models.CASCADE, related_name="movimientos"
    )
    tipo = models.CharField(max_length=12, choices=TIPOS)
    origen_categoria = models.ForeignKey(
        "Categoria", on_delete=models.PROTECT, related_name="movimientos_origen"
    )
    destino_categoria = models.ForeignKey(
        "Categoria", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="movimientos_destino",
    )
    jugadores_plantilla = models.PositiveIntegerField(
        default=0, verbose_name="Jugadores en plantilla al cierre",
        help_text="Tamaño de la plantilla del equipo cuando se registró el movimiento (referencia para el cupo de transferencia en ascensos)."
    )
    regla_activa = models.BooleanField(
        default=True, verbose_name="Vigencia de la regla",
        help_text="Mientras esté activa, los jugadores de este equipo quedan restringidos por este movimiento. "
                  "Desactívala cuando los torneos (Copa/Liga) para los que aplicaba ya hayan pasado."
    )
    cupo_porcentaje = models.PositiveIntegerField(
        default=50, verbose_name="Cupo de transferencia (%)",
        help_text="Porcentaje de la plantilla que puede cambiarse a otro equipo en un ascenso (50% por defecto). "
                  "Ajusta si uno de los torneos ya pasó y sólo resta un cupo menor o la regla ya se cumplió."
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Movimiento de equipo"
        verbose_name_plural = "Movimientos de equipos"
        ordering = ["-temporada__fecha_inicio", "equipo__nombre"]
        unique_together = ["temporada", "equipo"]

    def __str__(self):
        return f"{self.equipo} -> {self.get_tipo_display()}"

    def cupo_50(self):
        """Tope de jugadores que pueden cambiarse a otro equipo en un ascenso
        según el porcentaje configurado (cupo_porcentaje) y la plantilla al cierre."""
        pct = self.cupo_porcentaje or 50
        return (self.jugadores_plantilla * pct) // 100

    def transferidos(self):
        """Jugadores de la plantilla que ya se registraron como principal en otro equipo."""
        if self.jugadores_plantilla <= 0:
            return 0
        ids_plantilla = list(
            JugadorEquipo.objects.filter(
                equipo_id=self.equipo_id, activo=True
            ).values_list("jugador_id", flat=True)
        )
        if not ids_plantilla:
            return 0
        return JugadorEquipo.objects.filter(
            jugador_id__in=ids_plantilla, activo=True,
        ).exclude(equipo=self.equipo).filter(es_principal=True).values_list(
            "jugador_id", flat=True
        ).distinct().count()


class SuspensionJugador(models.Model):
    """Suspensión registrada manualmente por el administrador de la liga.

    Cuenta los próximos N partidos del equipo suspendido en la categoría;
    si se deja el equipo vacío, los N partidos se cuentan como jornadas
    completas de la categoría (cualquier equipo que juegue esa fecha).
    Si la temporada termina sin cumplirse, el saldo se arrastra a la
    siguiente temporada de la misma categoría.
    """
    jugador = models.ForeignKey(
        "Jugador", on_delete=models.CASCADE, related_name="suspensiones_manuales"
    )
    categoria = models.ForeignKey(
        "Categoria", on_delete=models.PROTECT, related_name="suspensiones_manuales"
    )
    equipo = models.ForeignKey(
        "Equipo", on_delete=models.CASCADE, related_name="suspensiones_manuales",
        blank=True, null=True,
        verbose_name="Equipo (rol donde cumple)",
        help_text="Opcional. Si se deja vacío, la suspensión cuenta las jornadas de toda la categoría.",
    )
    temporada = models.ForeignKey(
        "Temporada", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="suspensiones_manuales",
        verbose_name="Temporada donde inicia",
    )
    jornadas = models.PositiveIntegerField(default=1, verbose_name="Jornadas de suspensión")
    vitalicia = models.BooleanField(default=False, verbose_name="De por vida",
        help_text="Si está activa, la suspensión nunca expira (expulsión de por vida).")
    motivo = models.TextField(blank=True, verbose_name="Motivo")
    activo = models.BooleanField(default=True, verbose_name="Activa")
    fecha_inicio = models.DateField(verbose_name="Inicio del conteo")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Suspensión manual"
        verbose_name_plural = "Suspensiones manuales"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.jugador} ({self.categoria}) - {self.jornadas} J"

    def consumidos(self):
        """Partidos finalizados (FIN) que descontaron la suspensión desde fecha_inicio.

        Con equipo: cuenta los partidos FIN de ese equipo en la categoría.
        Sin equipo: cuenta las jornadas distintas de la categoría con al
        menos un partido FIN (una jornada = un partido de la suspensión).
        """
        from django.db.models import Q
        qs = Partido.objects.filter(
            temporada__categoria_id=self.categoria_id,
            temporada__fecha_inicio__gte=self.fecha_inicio,
            estado="FIN",
        )
        if self.equipo_id:
            qs = qs.filter(Q(equipo_local=self.equipo) | Q(equipo_visitante=self.equipo))
            return qs.count()
        return qs.order_by().values("jornada_id").distinct().count()

    def restantes(self):
        """Jornadas que faltan por cumplir (0 si ya cumplió o está pausada).

        Para suspensiones de por vida siempre devuelve 1 mientras estén
        activas: nunca se cumplan."""
        if not self.activo:
            return 0
        if self.vitalicia:
            return 1
        return max(0, self.jornadas - self.consumidos())

    def vigente(self):
        return self.restantes() > 0


class JugadorHerencia(models.Model):
    """Registra el historial heredado de un jugador al iniciar el sistema.

    Se usa solo una vez al principio para registrar jugadores que ya tenían
    un castigo, o jugadores de equipos que ascendieron, descendieron o se
    dieron de baja antes de tener el sistema.

    Tipo:
    - CASTIGADO: registrado como expulsado en la categoría indicada.
      Si lleva jornadas, se crea una SuspensJugador que bloquea
      en TODAS las categorías hasta cumplirla o levantarla.
    - ASCENSO / DESCENSO: el jugador puede registrarse solo en la
      categoría indicada o una inferior; si cambia de equipo, se
      aplican las mismas reglas que un movimiento real.
    - DESAPARECE: solo puede jugar en la categoría indicada o la
      inmediata inferior.
    """
    TIPOS = [
        ("CASTIGADO", "Castigado (expulsado del equipo)"),
        ("VITALICIO", "Expulsado de por vida"),
        ("ASCENSO", "Ascendido (desde otra categoría)"),
        ("DESCENSO", "Descendido (desde otra categoría)"),
        ("DESAPARECE", "Equipo se dio de baja"),
    ]

    jugador = models.ForeignKey(
        Jugador, on_delete=models.CASCADE, related_name="herencia"
    )
    tipo = models.CharField(max_length=12, choices=TIPOS)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="jugadores_heredados",
        verbose_name="Categoría del evento",
        help_text="Categoría donde se castigó / ascendió / descendió / se dio de baja."
    )
    jornadas = models.PositiveIntegerField(
        default=0, verbose_name="Jornadas de castigo restantes",
        help_text="Opcional: jornadas que le faltan de cumplir. "
                  "Si se pone un número mayor a 0, se crea una suspensión que bloquea al jugador en toda la liga."
    )
    motivo = models.TextField(blank=True, verbose_name="Motivo")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Jugador heredado"
        verbose_name_plural = "Jugadores heredados"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.jugador} — {self.get_tipo_display()} ({self.categoria})"


@deconstructible
class RawCloudinaryStorage(Storage):
    def __init__(self, folder=""):
        self.folder = folder

    def _save(self, name, content):
        import cloudinary.uploader
        try:
            content.name = "Reglamento"
        except Exception:
            pass
        options = {"resource_type": "raw", "public_id": "Reglamento", "overwrite": True}
        if self.folder:
            options["folder"] = self.folder
        return cloudinary.uploader.upload(content, **options)["public_id"]

    def open(self, name, mode="rb"):
        import requests
        from cloudinary.utils import cloudinary_url
        from django.core.files.base import ContentFile
        url = cloudinary_url(name, resource_type="raw", secure=True)[0]
        response = requests.get(url)
        response.raise_for_status()
        file = ContentFile(response.content)
        file.name = name
        return file

    def url(self, name):
        from cloudinary.utils import cloudinary_url
        return cloudinary_url(name, resource_type="raw", secure=True)[0]

    def exists(self, name):
        import requests
        from cloudinary.utils import cloudinary_url
        return requests.head(cloudinary_url(name, resource_type="raw", secure=True)[0]).status_code == 200

    def size(self, name):
        import requests
        from cloudinary.utils import cloudinary_url
        response = requests.head(cloudinary_url(name, resource_type="raw", secure=True)[0])
        return int(response.headers.get("content-length", 0)) if response.status_code == 200 else None

    def delete(self, name):
        import cloudinary.uploader
        return cloudinary.uploader.destroy(name, resource_type="raw").get("result") == "ok"


class ConfiguracionLiga(models.Model):
    nombre_liga = models.CharField(max_length=200, default="Mi Liga")
    segunda_linea = models.CharField(max_length=200, blank=True, default="",
        verbose_name="Segunda línea del nombre",
        help_text="Opcional. Se muestra centrado bajo el nombre (ej: 'Juventino Rosas'). Si se deja vacío se divide el nombre automáticamente.")
    logo = models.ImageField(upload_to="ligas/", blank=True, null=True)
    direccion = models.TextField(blank=True)
    telefonos = models.TextField(blank=True, help_text="Teléfonos de contacto separados por coma")
    email_provider = models.CharField(
        max_length=20, default="google",
        choices=[("google", "Google SMTP"), ("sendgrid", "SendGrid")],
        verbose_name="Proveedor de correo"
    )
    # Google SMTP
    email_smtp_host = models.CharField(max_length=200, blank=True, default="")
    email_smtp_port = models.IntegerField(default=587)
    email_smtp_user = models.CharField(max_length=200, blank=True, default="")
    email_smtp_password = models.CharField(max_length=200, blank=True, default="")
    email_use_tls = models.BooleanField(default=True)
    email_from = models.EmailField(blank=True, default="")
    # SendGrid
    email_sendgrid_host = models.CharField(max_length=200, blank=True, default="smtp.sendgrid.net")
    email_sendgrid_port = models.IntegerField(default=587)
    email_sendgrid_user = models.CharField(max_length=200, blank=True, default="apikey")
    email_sendgrid_password = models.CharField(max_length=200, blank=True, default="")
    email_sendgrid_use_tls = models.BooleanField(default=True, verbose_name="Usar TLS (SendGrid)")
    enviar_solo_jornada_actual = models.BooleanField(
        default=False, verbose_name="Enviar solo la jornada actual",
        help_text="Al enviar roles por correo, enviar solo los partidos de la jornada actual o próxima pendiente"
    )
    ticket_ancho_mm = models.IntegerField(default=58, choices=[(58, "58 mm"), (88, "88 mm")], verbose_name="Ancho del ticket (mm)")
    ticket_encabezado = models.TextField(default="", blank=True, verbose_name="Encabezado del ticket", help_text="Texto que aparece arriba del ticket (ej. nombre de la liga)")
    ticket_pie = models.TextField(default="¡Gracias por su visita!", blank=True, verbose_name="Pie del ticket", help_text="Texto al final del ticket (ej. Gracias por su visita)")
    correo_electronico = models.EmailField(blank=True, default="", verbose_name="Correo electrónico de contacto")
    redes_sociales = models.TextField(blank=True, default="", verbose_name="Redes sociales", help_text="Enlaces a redes sociales (uno por línea)")
    facebook_page_id = models.CharField(max_length=200, blank=True, default="", verbose_name="ID de página de Facebook",
        help_text="Ej: 123456789012345 (lo encuentras en la sección 'About' de tu página de Facebook)")
    facebook_access_token = models.CharField(max_length=500, blank=True, default="", verbose_name="Access Token de Facebook",
        help_text="Token de página de Facebook Graph API. "
                  "Para obtenerlo: 1) Crea una App en https://developers.facebook.com, "
                  "2) Ve a 'Graph API Explorer', selecciona tu app y página, "
                  "3) Genera un Page Access Token con permisos 'pages_manage_posts' y 'pages_read_engagement'.")
    reglamento = models.FileField(storage=RawCloudinaryStorage(folder="reglamentos"), upload_to="reglamentos/", blank=True, null=True, verbose_name="Reglamento (PDF)",
        help_text="Archivo PDF del reglamento de la liga. Visible para todos los usuarios.")

    database_url = models.URLField(max_length=500, blank=True, default="", verbose_name="Database URL",
        help_text="URL completa de conexión a la base de datos. Ej: postgresql://user:pass@host/db?sslmode=require. Requiere reiniciar el servidor tras cambiar.")
    cloudinary_cloud_name = models.CharField(max_length=200, blank=True, default="", verbose_name="Cloudinary Cloud Name")
    cloudinary_api_key = models.CharField(max_length=200, blank=True, default="", verbose_name="Cloudinary API Key")
    cloudinary_api_secret = models.CharField(max_length=500, blank=True, default="", verbose_name="Cloudinary API Secret")
    firebase_service_account_json = models.TextField(blank=True, default="", verbose_name="Firebase Service Account JSON",
        help_text="Pega aquí el JSON completo de la service account de Firebase. Se usa para enviar notificaciones push.")
    webpush_vapid_private_key = models.TextField(blank=True, default="", verbose_name="Clave privada VAPID (Web Push)",
        help_text="Clave privada VAPID para notificaciones Web Push (PWA). Se genera automáticamente; no compartir.")
    webpush_vapid_public_key = models.TextField(blank=True, default="", verbose_name="Clave pública VAPID (Web Push)",
        help_text="Clave pública VAPID (applicationServerKey) que usan los navegadores al suscribirse a notificaciones Web Push. Se genera automáticamente.")

    class Meta:
        verbose_name = "Configuración de la Liga"
        verbose_name_plural = "Configuración de la Liga"

    def __str__(self):
        return self.nombre_liga

    @classmethod
    def obtener(cls):
        from django.db import connection, ProgrammingError
        try:
            obj, _ = cls.objects.get_or_create(pk=1)
            return obj
        except ProgrammingError as e:
            if "does not exist" in str(e):
                with connection.cursor() as cur:
                    cur.execute("""
                        ALTER TABLE league_configuracionliga
                        ADD COLUMN IF NOT EXISTS email_provider varchar(20) NOT NULL DEFAULT 'google';
                    """)
                    cur.execute("""
                        ALTER TABLE league_configuracionliga
                        ADD COLUMN IF NOT EXISTS email_sendgrid_host varchar(200) NOT NULL DEFAULT '';
                    """)
                    cur.execute("""
                        ALTER TABLE league_configuracionliga
                        ADD COLUMN IF NOT EXISTS email_sendgrid_port integer NOT NULL DEFAULT 587;
                    """)
                    cur.execute("""
                        ALTER TABLE league_configuracionliga
                        ADD COLUMN IF NOT EXISTS email_sendgrid_user varchar(200) NOT NULL DEFAULT '';
                    """)
                    cur.execute("""
                        ALTER TABLE league_configuracionliga
                        ADD COLUMN IF NOT EXISTS email_sendgrid_password varchar(200) NOT NULL DEFAULT '';
                    """)
                    cur.execute("""
                        ALTER TABLE league_configuracionliga
                        ADD COLUMN IF NOT EXISTS email_sendgrid_use_tls boolean NOT NULL DEFAULT true;
                    """)
                obj, _ = cls.objects.get_or_create(pk=1)
                return obj
            raise

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        if self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret:
            import cloudinary
            cloudinary.config(
                cloud_name=self.cloudinary_cloud_name,
                api_key=self.cloudinary_api_key,
                api_secret=self.cloudinary_api_secret,
                secure=True,
            )

    def get_active_smtp_config(self):
        if self.email_provider == "sendgrid":
            return {
                "host": self.email_sendgrid_host or "smtp.sendgrid.net",
                "port": self.email_sendgrid_port or 587,
                "user": self.email_sendgrid_user or "apikey",
                "password": self.email_sendgrid_password,
                "use_tls": self.email_sendgrid_use_tls,
                "from_email": self.email_from,
            }
        return {
            "host": self.email_smtp_host,
            "port": self.email_smtp_port,
            "user": self.email_smtp_user,
            "password": self.email_smtp_password,
            "use_tls": self.email_use_tls,
            "from_email": self.email_from,
        }


class SuscripcionEmail(models.Model):
    email = models.EmailField()
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="suscripciones"
    )
    categorias = models.ManyToManyField(Categoria, blank=True)
    recibir_roles = models.BooleanField(default=True, verbose_name="Recibir rol de juegos semanal")
    recibir_estadisticas = models.BooleanField(default=True, verbose_name="Recibir estadísticas")
    token = models.CharField(max_length=100, unique=True, default=uuid.uuid4, editable=False)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Suscripción de Correo"
        verbose_name_plural = "Suscripciones de Correo"

    def __str__(self):
        return f"{self.email} - {'Activo' if self.activo else 'Inactivo'}"


class CampoIndisponibilidad(models.Model):
    campo = models.ForeignKey(Campo, on_delete=models.CASCADE, related_name="indisponibilidades")
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    motivo = models.TextField(blank=True, verbose_name="Motivo")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Indisponibilidad de Campo"
        verbose_name_plural = "Indisponibilidades de Campos"
        ordering = ["-fecha_desde"]

    def __str__(self):
        return f"{self.campo.nombre}: {self.fecha_desde} - {self.fecha_hasta}"


class JugadorPartido(models.Model):
    partido = models.ForeignKey(Partido, on_delete=models.CASCADE, related_name="participaciones")
    jugador = models.ForeignKey(Jugador, on_delete=models.CASCADE)
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE)
    titular = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Participación de Jugador"
        verbose_name_plural = "Participaciones de Jugadores"
        unique_together = ["partido", "jugador"]

    def __str__(self):
        return f"{self.jugador} - {'Titular' if self.titular else 'Suplente'} ({self.partido})"


class DeviceToken(models.Model):
    PLATFORMS = [
        ("android", "Android"),
        ("ios", "iOS"),
        ("web", "Web"),
        ("pwa", "PWA / Web Push"),
    ]
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="device_tokens", null=True, blank=True,
    )
    token = models.CharField(max_length=500, unique=True)
    device_id = models.CharField(max_length=36, default='', db_index=True, blank=True, null=True,
        verbose_name="ID de dispositivo",
        help_text="UUID generado por el cliente para identificar el dispositivo")
    plataforma = models.CharField(max_length=10, choices=PLATFORMS, default="android")
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)
    es_invitado = models.BooleanField(default=False, verbose_name="Es invitado",
        help_text="Registrado como invitado sin cuenta completa")
    nombre = models.CharField(max_length=100, blank=True, verbose_name="Nombre o apodo")
    telefono = models.CharField(max_length=20, blank=True, verbose_name="Teléfono")
    email = models.EmailField(blank=True, default="", verbose_name="Correo",
        help_text="Si se captura, el invitado también recibe por correo el rol de juegos de sus categorías")
    categorias = models.ManyToManyField(
        "Categoria", blank=True, verbose_name="Categorías de interés",
        help_text="Categorías sobre las que quiere recibir notificaciones"
    )
    webpush_endpoint = models.TextField(blank=True, default="", verbose_name="Endpoint Web Push",
        help_text="Endpoint de suscripción Web Push del navegador (PWA / iPhone)")
    webpush_p256dh = models.TextField(blank=True, default="", verbose_name="Clave p256dh (Web Push)",
        help_text="Clave pública de cifrado de la suscripción Web Push")
    webpush_auth = models.TextField(blank=True, default="", verbose_name="Clave auth (Web Push)",
        help_text="Secreto de autenticación de la suscripción Web Push")

    class Meta:
        verbose_name = "Token de dispositivo"
        verbose_name_plural = "Tokens de dispositivos"

    def __str__(self):
        label = self.nombre or self.token[:20]
        return f"{label} ({self.plataforma})"


class PushLog(models.Model):
    TIPO_CHOICES = [
        ("SEND", "Envío directo"),
        ("PARTIDO_FIN", "Partido finalizado"),
        ("RECORDATORIO", "Recordatorio 30 min"),
        ("SUSPENSION", "Suspensión / pendiente"),
        ("WEBPUSH", "Web Push (PWA)"),
    ]
    hora = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    partido_id = models.IntegerField(null=True, blank=True)
    categoria = models.CharField(max_length=200, blank=True)
    total_activos = models.IntegerField(null=True, blank=True)
    tokens_encontrados = models.IntegerField(null=True, blank=True)
    guests_incluidos = models.IntegerField(null=True, blank=True)
    success = models.IntegerField(null=True, blank=True)
    failure = models.IntegerField(null=True, blank=True)
    detalle = models.TextField(blank=True)
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Log de Push"
        verbose_name_plural = "Logs de Push"
        ordering = ["-hora"]

    def __str__(self):
        return f"[{self.tipo}] {self.hora}"


class OfflineToken(models.Model):
    """Token para modo offline de la app Android (árbitros)."""
    usuario = models.ForeignKey(
        "accounts.Usuario", on_delete=models.CASCADE, related_name="offline_tokens"
    )
    token = models.CharField(max_length=64, unique=True)
    creado = models.DateTimeField(auto_now_add=True)
    expira = models.DateTimeField()
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Token Offline"
        verbose_name_plural = "Tokens Offline"

    def __str__(self):
        return f"OfflineToken {self.usuario_id} ({self.expira:%d/%m/%Y})"
