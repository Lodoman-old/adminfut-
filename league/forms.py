import json

from django import forms
from django.utils.timezone import localtime, is_aware, make_aware
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import Categoria, Temporada, Grupo, Equipo, Jugador, JugadorEquipo, Campo, Arbitro, PeriodoAltas, Partido, HorarioFijoEquipo
from datetime import date


class TemporadaForm(forms.ModelForm):
    class Meta:
        model = Temporada
        fields = ["nombre", "categoria", "fecha_inicio", "fecha_fin", "activa", "tipo_rol", "vueltas", "num_grupos", "tipo_competencia", "num_clasificados", "es_prueba", "jornadas_limite_pago", "goles_default", "min_jugadores", "cambios_permitidos", "max_titulares", "ida_vuelta", "final_ida_vuelta", "criterio_liguilla", "min_porcentaje_liguilla", "clasificacion_por_grupos"]
        labels = {
            "es_prueba": "M. Prueba",
        }
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "fecha_inicio": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "fecha_fin": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "activa": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "tipo_rol": forms.Select(attrs={"class": "form-select"}),
            "vueltas": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "num_grupos": forms.NumberInput(attrs={"class": "form-control", "min": 2}),
            "tipo_competencia": forms.Select(attrs={"class": "form-select"}),
            "num_clasificados": forms.NumberInput(attrs={"class": "form-control", "min": 2}),
            "es_prueba": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "jornadas_limite_pago": forms.NumberInput(attrs={"class": "form-control", "min": 1, "placeholder": "Ej: 5"}),
            "goles_default": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "min_jugadores": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "cambios_permitidos": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "max_titulares": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "ida_vuelta": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "final_ida_vuelta": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "criterio_liguilla": forms.Select(attrs={"class": "form-select"}),
            "min_porcentaje_liguilla": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 100, "placeholder": "Ej: 20"}),
            "clasificacion_por_grupos": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        }

    def clean(self):
        cd = super().clean()
        if cd.get("tipo_rol") == "GRUPOS" and (not cd.get("num_grupos") or cd["num_grupos"] < 2):
            self.add_error("num_grupos", "Debe haber al menos 2 grupos para el tipo 'Por Grupos'.")
        return cd


class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = ["nombre", "categoria", "logo", "activo", "campo_rancheria"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "logo": forms.FileInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "campo_rancheria": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["campo_rancheria"].queryset = self.fields["campo_rancheria"].queryset.filter(
            activo=True, es_rancheria=True
        )


def _get_allowed_secondary_categories(equipo_principal, jugador=None):
    """
    Retorna las categorías en las que un jugador puede registrarse como
    secundario, considerando TODAS las categorías en las que ya participa
    (principal + secundarias existentes).

    - Las categorías donde el jugador YA tiene un equipo secundario
      siempre se incluyen (para poder ver su registro actual).
    - Las categorías NUEVAS solo se incluyen si son compatibles
      (en cualquier dirección) con CADA UNA de las categorías existentes.
    """
    from .models import Categoria
    cat = equipo_principal.categoria

    existing_cat_ids = {cat.id}
    existing_secondary_ids = set()
    if jugador and jugador.pk:
        for r in jugador.registros_equipo.filter(es_principal=False).select_related("equipo__categoria"):
            existing_cat_ids.add(r.equipo.categoria_id)
            existing_secondary_ids.add(r.equipo.categoria_id)

    all_cats = list(Categoria.objects.prefetch_related("categorias_compatibles").all())
    forward_map = {}
    for c in all_cats:
        forward_map[c.id] = set(c.categorias_compatibles.values_list("id", flat=True))
    reverse_map = {}
    for c in all_cats:
        for compat_id in forward_map[c.id]:
            reverse_map.setdefault(compat_id, set()).add(c.id)

    candidate_ids = forward_map.get(cat.id, set()) | reverse_map.get(cat.id, set())

    allowed = []
    for cid in candidate_ids:
        if cid in existing_secondary_ids:
            allowed.append(cid)
        elif cid not in existing_cat_ids:
            if all(
                cid in forward_map.get(existing_cid, set())
                or cid in reverse_map.get(existing_cid, set())
                for existing_cid in existing_cat_ids
            ):
                allowed.append(cid)

    return Categoria.objects.filter(id__in=allowed)


class JugadorForm(forms.ModelForm):
    secondary_data = forms.CharField(
        widget=forms.HiddenInput(attrs={"id": "id_secondary_data"}),
        required=False,
        label="",
    )

    class Meta:
        model = Jugador
        fields = ["nombre", "apellido", "curp", "foto", "fecha_nacimiento", "posicion", "equipo", "dorsal", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "apellido": forms.TextInput(attrs={"class": "form-control"}),
            "curp": forms.TextInput(attrs={"class": "form-control", "maxlength": 18, "placeholder": "Ej: AXXX000101HDFXXX00"}),
            "foto": forms.FileInput(attrs={"class": "form-control"}),
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "posicion": forms.Select(attrs={"class": "form-select"}),
            "equipo": forms.Select(attrs={"class": "form-select", "id": "id_equipo_principal"}),
            "dorsal": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.compat_fields = []

        inst = self.instance
        equipo_inicial = inst.equipo if inst and inst.pk else None

        if self.data.get("equipo"):
            try:
                eq_id = int(self.data.get("equipo"))
                equipo_inicial = Equipo.objects.get(id=eq_id)
            except (ValueError, Equipo.DoesNotExist):
                pass

        if equipo_inicial:
            cat = equipo_inicial.categoria
            cat_ids = [cat.id] + list(cat.categorias_compatibles.values_list("id", flat=True))
            self.fields["equipo"].queryset = Equipo.objects.filter(categoria_id__in=cat_ids, activo=True)

        # Poblar secondary_data con registros existentes (para edición)
        if inst and inst.pk:
            existing = []
            for r in inst.registros_equipo.filter(es_principal=False).select_related("equipo__categoria"):
                existing.append({"categoria_id": r.equipo.categoria_id, "equipo_id": r.equipo.id})
            if existing and not self.data.get("secondary_data"):
                self.fields["secondary_data"].initial = json.dumps(existing)

    @staticmethod
    def _jugador_ha_jugado_en_temporada(jugador, temporada, equipo=None):
        from .models import JugadorPartido
        qs = JugadorPartido.objects.filter(
            jugador=jugador,
            partido__temporada=temporada,
        )
        if equipo is not None:
            qs = qs.filter(equipo=equipo)
        return qs.exists()

    def clean_equipo(self):
        equipo = self.cleaned_data.get("equipo")
        if self.instance and self.instance.suspendido_pago:
            raise ValidationError(
                "El jugador está suspendido por adeudo de multa. "
                "Debe liquidar la multa en el módulo de Ingresos (POS) para poder ser registrado."
            )
        if self.instance and self.instance.pk and self.instance.equipo_id != equipo.id:
            cat_old = self.instance.equipo.categoria
            temp_activa = Temporada.objects.filter(categoria=cat_old, iniciada=True, finalizada=False).first()
            if temp_activa:
                ha_jugado = self._jugador_ha_jugado_en_temporada(self.instance, temp_activa, self.instance.equipo)
                periodo_abierto = temp_activa.periodos_altas.filter(activo=True).exists()
                if not periodo_abierto:
                    raise ValidationError(
                        f"No puedes cambiar el equipo del jugador mientras haya una temporada en curso "
                        f"en {cat_old.nombre}. Espera al periodo de altas entre temporadas."
                    )
                if ha_jugado:
                    raise ValidationError(
                        f"No puedes cambiar el equipo del jugador porque ya tiene participaciones "
                        f"registradas en la temporada actual de {cat_old.nombre}."
                    )
            # No se puede entrar a una categoría con temporada en curso
            if equipo and Temporada.objects.filter(categoria=equipo.categoria, iniciada=True, finalizada=False).exists():
                raise ValidationError(
                    f"La categoría {equipo.categoria.nombre} ya tiene una temporada en curso."
                )
        return equipo

    def clean(self):
        cleaned = super().clean()
        curp = cleaned.get("curp")
        nombre = cleaned.get("nombre")
        apellido = cleaned.get("apellido")
        fecha_nac = cleaned.get("fecha_nacimiento")
        instance = self.instance

        if curp:
            qs = Jugador.objects.filter(curp=curp)
            if instance and instance.pk:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                self.add_error("curp", f"Ya existe un jugador registrado con este CURP: {qs.first()}")
        elif nombre and apellido and fecha_nac:
            qs = Jugador.objects.filter(
                nombre__iexact=nombre,
                apellido__iexact=apellido,
                fecha_nacimiento=fecha_nac,
            )
            if instance and instance.pk:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                self.add_error("nombre", f"Ya existe un jugador con los mismos datos: {qs.first()}")
        return cleaned

    def _edad_desde_fecha(self, fn):
        """Calcula edad desde una fecha de nacimiento (date) o None"""
        if not fn:
            return None
        from datetime import date as dt_date
        today = dt_date.today()
        return today.year - fn.year - ((today.month, today.day) < (fn.month, fn.day))

    @staticmethod
    def _normalize_curp_str(s):
        """Limpia acentos, ñ y diéresis para comparación CURP."""
        import unicodedata
        s = unicodedata.normalize('NFKD', s.upper()).encode('ASCII', 'ignore').decode('ASCII')
        s = s.replace('Ñ', 'X')
        return s

    @staticmethod
    def _first_vowel(s):
        """Primera vocal interna después de la primera letra."""
        for ch in s[1:]:
            if ch in 'AEIOU':
                return ch
        return 'X'

    @staticmethod
    def _first_consonant(s):
        """Primera consonante interna después de la primera letra."""
        for ch in s[1:]:
            if ch not in 'AEIOU':
                return ch
        return 'X'

    # Claves de entidad federativa (posiciones 12-13 de la CURP) + NE extranjero
    ENTIDADES_CURP = frozenset({
        "AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG", "GT", "GR",
        "HG", "JC", "MC", "MN", "MS", "NT", "NL", "OC", "PL", "QT", "QR", "SP",
        "SL", "SR", "TC", "TS", "TL", "VZ", "YN", "ZS", "NE",
    })

    @staticmethod
    def _calcular_digito_curp(curp):
        """Calcula el dígito verificador (posición 18) según el algoritmo de RENAPO."""
        tabla = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"
        # Peso: 18 para la 1ª letra, 17 para la 2ª ... 2 para la 17ª
        suma = sum(tabla.index(ch) * (18 - i) for i, ch in enumerate(curp[:17]))
        return (10 - (suma % 10)) % 10

    @classmethod
    def _errores_estructura_curp(cls, curp):
        """Valida estructura + entidad + dígito verificador. Devuelve lista de errores."""
        import re
        curp = curp.upper()
        errores = []
        if len(curp) != 18:
            return ["El CURP debe tener exactamente 18 caracteres."]
        # 17ª posición: dígito homonimia (0-9 nacidos ≤1999, A-Z nacidos ≥2000); 18ª: dígito verificador
        if not re.match(r'^[A-Z][AEIOU][A-Z][A-Z]\d{6}[HM][A-Z]{2}[A-Z]{3}[0-9A-Z]\d$', curp):
            errores.append("Formato de CURP inválido. Ej: AXXX000101HDFXXX00")
            return errores
        entidad = curp[11:13]
        if entidad not in cls.ENTIDADES_CURP:
            errores.append(f"Entidad de nacimiento inválida '{entidad}'.")
        try:
            if cls._calcular_digito_curp(curp) != int(curp[17]):
                errores.append("El CURP no pasa el dígito verificador (posible error de captura).")
        except Exception:
            pass
        return errores

    def _validar_curp_contra_datos(self, curp, nombre, apellido, fecha_nac):
        """Valida que el CURP codificado coincida con nombre, apellido y fecha."""
        curp = curp.upper()
        curp_nombre = curp[3]          # 4ª letra = inicial del nombre
        curp_paterno = curp[0]         # 1ª letra = inicial apellido paterno
        curp_vocal = curp[1]           # 2ª letra = 1ª vocal apellido paterno
        curp_materno = curp[2]         # 3ª letra = inicial apellido materno
        curp_anio = curp[4:6]          # año (2 dígitos)
        curp_mes = curp[6:8]           # mes
        curp_dia = curp[8:10]          # día

        # Normalizar datos ingresados
        n_nombre = self._normalize_curp_str(nombre)
        n_apellido = self._normalize_curp_str(apellido)

        # Separar apellido en paterno + materno
        partes = n_apellido.split()
        paterno = partes[0] if partes else ""
        materno = partes[1] if len(partes) > 1 else ""

        # Validar iniciales
        errores = []
        if paterno and curp_paterno != paterno[0]:
            errores.append(f"La 1ª letra del apellido paterno debería ser '{paterno[0]}' (CURP dice '{curp_paterno}')")
        if paterno and curp_vocal != self._first_vowel(paterno):
            errores.append(f"La 1ª vocal del apellido paterno debería ser '{self._first_vowel(paterno)}' (CURP dice '{curp_vocal}')")
        if materno and curp_materno != materno[0]:
            errores.append(f"La 1ª letra del apellido materno debería ser '{materno[0]}' (CURP dice '{curp_materno}')")
        if n_nombre and curp_nombre != n_nombre[0]:
            errores.append(f"La 1ª letra del nombre debería ser '{n_nombre[0]}' (CURP dice '{curp_nombre}')")

        # Validar fecha de nacimiento
        if fecha_nac:
            anio_curp = int(curp_anio)
            anio_completo = fecha_nac.year
            anio_2d = anio_completo % 100
            if anio_2d != anio_curp:
                errores.append(f"El año en CURP es '{curp_anio}' pero el año capturado es {anio_2d:02d}")
            mes_curp = int(curp_mes)
            if mes_curp != fecha_nac.month:
                errores.append(f"El mes en CURP es '{curp_mes}' pero el mes capturado es {fecha_nac.month:02d}")
            dia_curp = int(curp_dia)
            if dia_curp != fecha_nac.day:
                errores.append(f"El día en CURP es '{curp_dia}' pero el día capturado es {fecha_nac.day:02d}")

        return errores

    def clean(self):
        cleaned = super().clean()
        self._age_violations = []

        # CURP: validar formato y coherencia con datos del jugador
        curp = cleaned.get("curp")
        if curp:
            errs_estructura = self._errores_estructura_curp(curp)
            if errs_estructura:
                self.add_error("curp", "; ".join(errs_estructura))
            else:
                curp = curp.upper()
                cleaned["curp"] = curp
                nombre_ok = cleaned.get("nombre", "").strip()
                apellido_ok = cleaned.get("apellido", "").strip()
                fecha_ok = cleaned.get("fecha_nacimiento")
                faltan = []
                if not nombre_ok:
                    faltan.append("Nombre")
                if not apellido_ok:
                    faltan.append("Apellido(s)")
                if not fecha_ok:
                    faltan.append("Fecha de nacimiento")
                if faltan:
                    self.add_error("curp",
                        f"Para validar el CURP debe capturar primero: {', '.join(faltan)}.")
                else:
                    errs = self._validar_curp_contra_datos(curp, nombre_ok, apellido_ok, fecha_ok)
                    if errs:
                        self.add_error("curp", "El CURP no coincide con los datos capturados: " + "; ".join(errs))

        # CURP obligatoria según las categorías (principal + secundarias)
        if not curp:
            cat_ids_req = set()
            equipo_prim = cleaned.get("equipo")
            if equipo_prim:
                cat_ids_req.add(equipo_prim.categoria_id)
            raw_sec = cleaned.get("secondary_data")
            if raw_sec:
                try:
                    parsed_sec = json.loads(raw_sec)
                    if isinstance(parsed_sec, list):
                        for item in parsed_sec:
                            if item.get("categoria_id"):
                                cat_ids_req.add(item["categoria_id"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if cat_ids_req:
                cats_oblig = list(Categoria.objects.filter(id__in=cat_ids_req, curp_obligatoria=True))
                if cats_oblig:
                    self.add_error("curp",
                        "El CURP es obligatorio para: " + ", ".join(c.nombre for c in cats_oblig) + ".")

        # Detect if fecha_nacimiento changed and check age violations
        if self.instance and self.instance.pk:
            old_fn = Jugador.objects.filter(pk=self.instance.pk).values_list("fecha_nacimiento", flat=True).first()
        else:
            old_fn = None
        new_fn = cleaned.get("fecha_nacimiento")
        birth_date_changed = old_fn and new_fn and old_fn != new_fn
        # Usar la NUEVA fecha (cleaned) para validar edad, no self.instance.edad()
        edad_a_validar = self._edad_desde_fecha(new_fn)

        equipo = cleaned.get("equipo")
        if equipo:
            cat = equipo.categoria
            # Reunir todas las categorías seleccionadas (principal + secundarias)
            cat_ids = {cat.id}

            # Parse secondary_data JSON
            secondary = {}
            raw = cleaned.get("secondary_data")
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        for item in parsed:
                            cid = item.get("categoria_id")
                            eid = item.get("equipo_id")
                            if cid and eid:
                                secondary[cid] = eid
                                cat_ids.add(cid)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Prefetch relaciones de compatibilidad
            cats = {c.id: c for c in Categoria.objects.filter(id__in=cat_ids).prefetch_related("categorias_compatibles")}
            forward_map = {}
            for cid, c in cats.items():
                forward_map[cid] = set(c.categorias_compatibles.values_list("id", flat=True))
            reverse_map = {}
            for cid, c in cats.items():
                for compat_id in forward_map[cid]:
                    reverse_map.setdefault(compat_id, set()).add(c.id)

            # Check compatibilidad: cada categoría debe ser compatible con TODAS las demás
            cat_id_list = list(cat_ids)
            for i in range(len(cat_id_list)):
                a = cat_id_list[i]
                for j in range(i + 1, len(cat_id_list)):
                    b = cat_id_list[j]
                    if (b not in forward_map.get(a, set()) and b not in reverse_map.get(a, set())
                            and a not in forward_map.get(b, set()) and a not in reverse_map.get(b, set())):
                        msg = f"{cats[a].nombre} y {cats[b].nombre} no son compatibles entre sí."
                        self.add_error("secondary_data", msg)

            # Validar cada equipo secundario
            for cid, eid in secondary.items():
                try:
                    eq_obj = Equipo.objects.get(id=eid)
                except Equipo.DoesNotExist:
                    self.add_error("secondary_data", f"Equipo {eid} no encontrado.")
                    continue
                if eq_obj.categoria_id != cid:
                    self.add_error("secondary_data", f"El equipo {eq_obj.nombre} no pertenece a la categoría {cats.get(cid, Categoria(id=cid)).nombre}.")
                    continue
                # Validar edad
                if edad_a_validar is not None:
                    c_obj = cats.get(cid)
                    if c_obj:
                        if c_obj.edad_minima is not None and edad_a_validar < c_obj.edad_minima:
                            if birth_date_changed:
                                self._age_violations.append({
                                    "categoria": c_obj, "equipo": eq_obj,
                                    "field": f"cat_{cid}",
                                    "motivo": f"Edad mínima {c_obj.edad_minima} años",
                                    "edad_jugador": edad_a_validar,
                                })
                            else:
                                self.add_error("secondary_data",
                                    f"{c_obj.nombre} requiere edad mínima de {c_obj.edad_minima} años. "
                                    f"El jugador tiene {edad_a_validar}.")
                        if c_obj.edad_maxima is not None and edad_a_validar > c_obj.edad_maxima:
                            if birth_date_changed:
                                self._age_violations.append({
                                    "categoria": c_obj, "equipo": eq_obj,
                                    "field": f"cat_{cid}",
                                    "motivo": f"Edad máxima {c_obj.edad_maxima} años",
                                    "edad_jugador": edad_a_validar,
                                })
                            else:
                                self.add_error("secondary_data",
                                    f"{c_obj.nombre} permite edad máxima de {c_obj.edad_maxima} años. "
                                    f"El jugador tiene {edad_a_validar}.")
                # Validar temporada en curso
                temp_activa_qs = Temporada.objects.filter(
                    categoria_id=cid, iniciada=True, finalizada=False
                )
                if temp_activa_qs.exists():
                    temp_obj = temp_activa_qs.first()
                    old_id = None
                    if self.instance and self.instance.pk:
                        old = self.instance.registros_equipo.filter(
                            equipo__categoria_id=cid, es_principal=False
                        ).first()
                        if old:
                            old_id = old.equipo_id
                    if old_id is not None and eid != old_id:
                        # Cambio de equipo: permitir solo si hay período abierto y no ha jugado
                        periodo_abierto = temp_obj.periodos_altas.filter(activo=True).exists()
                        ha_jugado = self._jugador_ha_jugado_en_temporada(self.instance, temp_obj, old.equipo)
                        if not periodo_abierto:
                            self.add_error("secondary_data",
                                f"No hay un período de altas activo en {cats[cid].nombre}. No se puede cambiar de equipo.")
                        elif ha_jugado:
                            self.add_error("secondary_data",
                                f"No puedes cambiar de equipo en {cats[cid].nombre} porque el jugador ya tiene participaciones registradas.")
                    elif old_id is None:
                        # Alta nueva: permitir solo si hay período abierto
                        periodo_abierto = temp_obj.periodos_altas.filter(activo=True).exists()
                        if not periodo_abierto:
                            self.add_error("secondary_data",
                                f"No puedes agregar un equipo en {cats[cid].nombre} porque no hay un período de altas activo.")

            # Validar edad del equipo principal
            def _validar_edad(equipo_check, field_name_check):
                c = equipo_check.categoria
                if c.edad_minima is not None and edad_a_validar is not None:
                    if edad_a_validar < c.edad_minima:
                        if birth_date_changed:
                            self._age_violations.append({
                                "categoria": c,
                                "equipo": equipo_check,
                                "field": field_name_check,
                                "motivo": f"Edad mínima {c.edad_minima} años",
                                "edad_jugador": edad_a_validar,
                            })
                        else:
                            self.add_error(field_name_check,
                                f"{c.nombre} requiere edad mínima de {c.edad_minima} años. "
                                f"El jugador tiene {edad_a_validar}.")
                if c.edad_maxima is not None and edad_a_validar is not None:
                    if edad_a_validar > c.edad_maxima:
                        if birth_date_changed:
                            self._age_violations.append({
                                "categoria": c,
                                "equipo": equipo_check,
                                "field": field_name_check,
                                "motivo": f"Edad máxima {c.edad_maxima} años",
                                "edad_jugador": edad_a_validar,
                            })
                        else:
                            self.add_error(field_name_check,
                                f"{c.nombre} permite edad máxima de {c.edad_maxima} años. "
                                f"El jugador tiene {edad_a_validar}.")
            _validar_edad(equipo, "equipo")

    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
        if commit:
            nuevo_principal = instance.equipo
            if nuevo_principal:
                instance.registros_equipo.filter(
                    equipo__categoria=nuevo_principal.categoria,
                    es_principal=False,
                ).delete()
                # Limpiar es_principal=True de otras categorías
                instance.registros_equipo.filter(es_principal=True
                ).exclude(equipo=nuevo_principal).delete()
            instance.registros_equipo.filter(es_principal=False).delete()

            raw = self.cleaned_data.get("secondary_data")
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        for item in parsed:
                            eid = item.get("equipo_id")
                            if eid:
                                try:
                                    eq = Equipo.objects.get(id=eid)
                                except Equipo.DoesNotExist:
                                    continue
                                JugadorEquipo.objects.create(
                                    jugador=instance, equipo=eq, es_principal=False,
                                )
                except (json.JSONDecodeError, TypeError):
                    pass
        return instance


class CampoForm(forms.ModelForm):
    class Meta:
        model = Campo
        fields = ["nombre", "direccion", "telefono_contacto", "activo", "es_rancheria", "observaciones", "fecha_estimada_retorno"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "direccion": forms.TextInput(attrs={"class": "form-control"}),
            "telefono_contacto": forms.TextInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "es_rancheria": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "observaciones": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "fecha_estimada_retorno": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }


class ArbitroForm(forms.ModelForm):
    crear_usuario = forms.BooleanField(
        required=False,
        label="Crear usuario del sistema con rol Árbitro",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        if inst and inst.pk and inst.usuario_id:
            self.fields["crear_usuario"].initial = True
            self.fields["crear_usuario"].disabled = True
            self.fields["crear_usuario"].help_text = "Ya tiene un usuario de sistema vinculado."

    class Meta:
        model = Arbitro
        fields = ["nombre", "apellido", "telefono", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "apellido": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        }


class PeriodoAltasForm(forms.ModelForm):
    class Meta:
        model = PeriodoAltas
        fields = ["temporada", "tipo", "fecha_inicio", "fecha_fin", "jornada_inicio", "jornada_fin", "extraordinario", "activo"]
        widgets = {
            "temporada": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "fecha_inicio": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "fecha_fin": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "jornada_inicio": forms.NumberInput(attrs={"class": "form-control"}),
            "jornada_fin": forms.NumberInput(attrs={"class": "form-control"}),
            "extraordinario": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["temporada"].queryset = Temporada.objects.filter(finalizada=False)


class PartidoForm(forms.ModelForm):
    fecha = forms.DateField(
        label="Fecha",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
    )
    hora = forms.TimeField(
        label="Hora",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "HH:MM"}),
        input_formats=["%H:%M", "%H:%M:%S"],
    )

    class Meta:
        model = Partido
        fields = ["temporada", "jornada", "es_amistoso", "equipo_local", "equipo_visitante", "campo", "arbitro", "goles_local", "goles_visitante", "estado"]
        widgets = {
            "temporada": forms.Select(attrs={"class": "form-select"}),
            "jornada": forms.Select(attrs={"class": "form-select"}),
            "es_amistoso": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "equipo_local": forms.Select(attrs={"class": "form-select"}),
            "equipo_visitante": forms.Select(attrs={"class": "form-select"}),
            "campo": forms.Select(attrs={"class": "form-select"}),
            "arbitro": forms.Select(attrs={"class": "form-select"}),
            "goles_local": forms.NumberInput(attrs={"class": "form-control", "min": 0, "disabled": True}),
            "goles_visitante": forms.NumberInput(attrs={"class": "form-control", "min": 0, "disabled": True}),
            "estado": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.fecha_hora:
            dt = self.instance.fecha_hora
            if is_aware(dt):
                dt = localtime(dt)
            self.fields["fecha"].initial = dt.date()
            self.fields["hora"].initial = dt.time().replace(microsecond=0)
        self.fields["goles_local"].disabled = True
        self.fields["goles_local"].required = False
        self.fields["goles_visitante"].disabled = True
        self.fields["goles_visitante"].required = False
        self.fields["temporada"].required = False
        self.fields["jornada"].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.es_amistoso:
            instance.temporada = None
            instance.jornada = None
        fecha = self.cleaned_data.get("fecha")
        hora = self.cleaned_data.get("hora")
        if fecha and hora:
            import datetime
            dt = datetime.datetime.combine(fecha, hora)
            instance.fecha_hora = make_aware(dt) if not is_aware(dt) else dt
        if commit:
            instance.save()
        return instance

    def clean(self):
        cleaned_data = super().clean()
        equipo_local = cleaned_data.get("equipo_local")
        equipo_visitante = cleaned_data.get("equipo_visitante")
        campo = cleaned_data.get("campo")
        temporada = cleaned_data.get("temporada")
        jornada = cleaned_data.get("jornada")
        es_amistoso = cleaned_data.get("es_amistoso")
        fecha = cleaned_data.get("fecha")
        hora = cleaned_data.get("hora")

        if equipo_local and equipo_visitante and equipo_local == equipo_visitante:
            raise ValidationError("El equipo local y visitante no pueden ser el mismo.")

        if fecha and hora:
            import datetime
            dt = datetime.datetime.combine(fecha, hora)
            dt_aware = make_aware(dt) if not is_aware(dt) else dt
            pk = self.instance.pk if self.instance else None

            def _changed(field_name, form_value):
                if not pk:
                    return True
                orig_val = getattr(self.instance, field_name, None)
                if field_name == "campo":
                    orig_pk = orig_val.pk if orig_val else None
                    form_pk = form_value.pk if hasattr(form_value, 'pk') else form_value
                    return orig_pk != form_pk
                if field_name == "fecha_hora":
                    if orig_val and form_value:
                        o = localtime(orig_val) if is_aware(orig_val) else orig_val
                        return o.date() != form_value.date() or o.time().replace(microsecond=0) != form_value.time().replace(microsecond=0)
                    return orig_val != form_value
                return orig_val != form_value

            if campo and _changed("campo", campo):
                dup = Partido.objects.filter(fecha_hora=dt_aware, campo=campo)
                if pk:
                    dup = dup.exclude(pk=pk)
                if dup.exists():
                    raise ValidationError(f"Ya existe un partido en {campo} en esa fecha y horario.")

            if equipo_local and _changed("equipo_local", equipo_local):
                dup_local = Partido.objects.filter(
                    Q(fecha_hora=dt_aware) & (Q(equipo_local=equipo_local) | Q(equipo_visitante=equipo_local))
                )
                if pk:
                    dup_local = dup_local.exclude(pk=pk)
                if dup_local.exists():
                    raise ValidationError(f"El equipo {equipo_local} ya tiene un partido en esa fecha y horario.")

            if equipo_visitante and _changed("equipo_visitante", equipo_visitante):
                dup_visit = Partido.objects.filter(
                    Q(fecha_hora=dt_aware) & (Q(equipo_local=equipo_visitante) | Q(equipo_visitante=equipo_visitante))
                )
                if pk:
                    dup_visit = dup_visit.exclude(pk=pk)
                if dup_visit.exists():
                    raise ValidationError(f"El equipo {equipo_visitante} ya tiene un partido en esa fecha y horario.")

        if not es_amistoso:
            if not temporada:
                raise ValidationError("Debes seleccionar una temporada para partidos de liga.")
            if temporada and jornada and jornada.temporada_id != temporada.id:
                raise ValidationError("La jornada seleccionada no pertenece a la temporada seleccionada.")

        arbitro = cleaned_data.get("arbitro")
        if arbitro and fecha and hora:
            import datetime
            dt = datetime.datetime.combine(fecha, hora)
            dt_aware = make_aware(dt) if not is_aware(dt) else dt
            dup_arbitro = Partido.objects.filter(fecha_hora=dt_aware, arbitro=arbitro)
            if pk:
                dup_arbitro = dup_arbitro.exclude(pk=pk)
            if dup_arbitro.exists():
                raise ValidationError(f"El árbitro {arbitro} ya está asignado a otro partido en esa fecha y horario.")

        return cleaned_data


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre", "descripcion", "rango_edad", "edad_minima", "edad_maxima", "genero", "activo", "es_principal", "curp_obligatoria", "min_jugadores", "max_jugadores", "categorias_compatibles", "campos_permitidos", "fondo_credencial"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "rango_edad": forms.TextInput(attrs={"class": "form-control"}),
            "edad_minima": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "edad_maxima": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "genero": forms.TextInput(attrs={"class": "form-control"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "es_principal": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "curp_obligatoria": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "min_jugadores": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "max_jugadores": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "categorias_compatibles": forms.SelectMultiple(attrs={"class": "form-select", "size": 4}),
            "campos_permitidos": forms.SelectMultiple(attrs={"class": "form-select", "size": 6}),
            "fondo_credencial": forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
        }

    dias_lunes = forms.BooleanField(required=False, label="Lunes")
    dias_martes = forms.BooleanField(required=False, label="Martes")
    dias_miercoles = forms.BooleanField(required=False, label="Miércoles")
    dias_jueves = forms.BooleanField(required=False, label="Jueves")
    dias_viernes = forms.BooleanField(required=False, label="Viernes")
    dias_sabado = forms.BooleanField(required=False, label="Sábado")
    dias_domingo = forms.BooleanField(required=False, label="Domingo")
    horarios_text = forms.CharField(required=False, label="Horarios (separados por coma, ej: 15:00, 17:00)",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "15:00, 17:00, 19:00"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.dias_juego:
                dias = self.instance.dias_juego
                mapa = {
                    "LUN": "dias_lunes", "MAR": "dias_martes", "MIE": "dias_miercoles",
                    "JUE": "dias_jueves", "VIE": "dias_viernes", "SAB": "dias_sabado",
                    "DOM": "dias_domingo",
                }
                for k, v in mapa.items():
                    if k in dias:
                        self.fields[v].initial = True
            if self.instance.horarios:
                self.fields["horarios_text"].initial = ", ".join(self.instance.horarios)

    def save(self, commit=True):
        instance = super().save(commit=False)
        dias = []
        mapa = {
            "dias_lunes": "LUN", "dias_martes": "MAR", "dias_miercoles": "MIE",
            "dias_jueves": "JUE", "dias_viernes": "VIE", "dias_sabado": "SAB",
            "dias_domingo": "DOM",
        }
        for field, code in mapa.items():
            if self.cleaned_data.get(field):
                dias.append(code)
        instance.dias_juego = dias
        horarios_str = self.cleaned_data.get("horarios_text", "")
        if horarios_str:
            instance.horarios = [h.strip() for h in horarios_str.split(",") if h.strip()]
        else:
            instance.horarios = []
        if commit:
            instance.save()
            self.save_m2m()
        return instance



