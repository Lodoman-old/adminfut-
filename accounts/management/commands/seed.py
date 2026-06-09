from django.core.management.base import BaseCommand
from accounts.models import Rol, Usuario
from league.models import Categoria, Equipo, Jugador, Campo
from finance.models import ConceptoIngreso
import random


class Command(BaseCommand):
    help = "Inicializa datos básicos del sistema"

    def handle(self, *args, **options):
        self._crear_roles()
        self._crear_categorias()
        self._crear_campos()
        self._poblar_equipos()
        self._poblar_jugadores()
        self._crear_conceptos()
        self.stdout.write(self.style.SUCCESS(f"Total: {Equipo.objects.count()} equipos, {Jugador.objects.count()} jugadores"))

    def _crear_roles(self):
        from accounts.models import get_permisos_flat
        flat = get_permisos_flat()
        admin_permisos = {key: True for key, _, _, _, _ in flat}
        admin_rol, _ = Rol.objects.get_or_create(nombre="Administrador", defaults={"permisos": admin_permisos})
        op_permisos = dict(admin_permisos)
        op_permisos.update({"gestion_roles": False, "gestion_usuarios": False})
        Rol.objects.get_or_create(nombre="Operador", defaults={"permisos": op_permisos})
        inv_permisos = {key: False for key, _, _, _, _ in flat}
        inv_permisos.update({"ver_finanzas": False})
        Rol.objects.get_or_create(nombre="Invitado", defaults={"permisos": inv_permisos})
        try:
            u = Usuario.objects.get(username="admin")
            u.rol = admin_rol; u.save()
        except Usuario.DoesNotExist:
            pass
        self.stdout.write(self.style.SUCCESS("Roles OK"))

    def _crear_categorias(self):
        datos = [
            ("Liga Mayor", "Categoría principal", "18+", "Masculino", False, 12, 26, ["SAB", "DOM"]),
            ("Liga Femenil", "Categoría femenil", "18+", "Femenino", False, 12, 26, ["SAB"]),
            ("Juvenil", "Categoría juvenil", "15-17", "Masculino", False, 12, 26, ["DOM"]),
            ("Liga Veteranos", "Categoría veteranos", "35+", "Masculino", True, 12, 26, ["SAB"]),
        ]
        for nombre, desc, edad, gen, principal, mini, maxi, dias in datos:
            Categoria.objects.update_or_create(
                nombre=nombre,
                defaults={"descripcion": desc, "rango_edad": edad, "genero": gen,
                          "es_principal": principal, "min_jugadores": mini, "max_jugadores": maxi,
                          "dias_juego": dias, "activo": True},
            )
        self.stdout.write(self.style.SUCCESS("Categorías actualizadas"))

    def _crear_campos(self):
        for n, d, t in [("Campo Municipal 1", "Av. Deportiva 100", "555-1001"),
                         ("Campo Municipal 2", "Av. Deportiva 200", "555-1002"),
                         ("Cancha Sintética A", "Calle Fútbol 50", "555-2001"),
                         ("Cancha Sintética B", "Calle Fútbol 60", "555-2002")]:
            Campo.objects.get_or_create(nombre=n, defaults={"direccion": d, "telefono_contacto": t})
        self.stdout.write(self.style.SUCCESS("Campos OK"))

    def _poblar_equipos(self):
        prefijos = ["Real", "Deportivo", "Atlético", "FC", "Club", "Sporting", "Universidad", "Academia",
                     "Los", "Las", "San", "Santa", "Nuevo", "Villa", "Monte", "Río", "Pueblo", "Cerro",
                     "Alto", "Bajo", "Loma", "Valle", "Cruz", "Palma", "Sol", "Luna", "Estrella", "Rayo"]
        sufijos = ["Madrid", "León", "Lagos", "Torres", "Blanco", "Negro", "Verde", "Rojo", "Azul",
                    "Oro", "Plata", "Bravo", "Norte", "Sur", "Este", "Oeste", "Unido", "Junior",
                    "Mayor", "Nacional", "América", "Libertad", "Victoria", "Gloria", "Furia", "Aurora"]
        posiciones = ["POR", "DEF", "DEF", "DEF", "DEF", "MED", "MED", "MED", "MED", "DEL", "DEL"]
        nombres_m = ["Carlos","Luis","Miguel","Jorge","Andrés","Diego","Pablo","Sergio","Fernando",
                      "Alejandro","Ricardo","Javier","Manuel","Roberto","David","Pedro","Juan","Antonio",
                      "Francisco","Rafael","Eduardo","Gustavo","Héctor","Iván","Julián","Leonardo","Marco",
                      "Néstor","Oscar","Rubén","Samuel","Tomás","Ulises","Víctor","Wilson","Xavier",
                      "Yahir","Zacarías","Adán","Benito","César","Daniel","Emilio","Felipe","Alan","Bruno",
                      "Christian","Damián","Elías","Fabián","Gabriel","Humberto","Ismael","Jesús","Kevin",
                      "Lorenzo","Mauricio","Noé","Octavio","Raúl","Saúl","Uriel","Vicente","Abel","Hugo",
                      "Ián","Mateo","Nicolás","Oliver","Santiago","Ángel","Brandon","Cristian","Emmanuel",
                      "Gael","Jared","Luis","Rafael","Diego"]
        apellidos = ["López","García","Hernández","Martínez","Ramírez","Torres","Flores","Ramos","Gómez",
                      "Díaz","Moreno","Álvarez","Romero","Sánchez","Cruz","Rodríguez","Pérez","Luna","Vega",
                      "Mendoza","Ríos","Ortiz","Delgado","Aguilar","Castro","Mora","Peña","Cabrera","Reyes",
                      "Nava","Serrano","Lara","Guerrero","Sandoval","Ibáñez","Palacios","Medina","Espinoza",
                      "Cortés","Maldonado","Salinas","Pacheco","Valenzuela","Navarro","Carrillo","Rangel",
                      "Quintana","Bautista","Fuentes","Villanueva","Covarrubias","Saucedo","Paredes","Becerra",
                      "Zamora","Tapia","Mejía","Hurtado","Castañeda","Llamas","Herrera","Vargas","Castro",
                      "Ponce","Acosta","Salazar","Delgado","Valencia","Cervantes","Jiménez"]
        categorias = list(Categoria.objects.all())
        # Usar get_or_create para equipos ya existentes
        equipos_existentes = set(Equipo.objects.values_list("nombre", "categoria_id"))
        random.seed(42)
        for cat in categorias:
            actuales = Equipo.objects.filter(categoria=cat).count()
            if actuales >= 12:
                self.stdout.write(f"  {cat.nombre}: {actuales} equipos (suficiente)")
                continue
            # Generar nombres únicos
            intentos = 0
            while Equipo.objects.filter(categoria=cat).count() < 12 and intentos < 100:
                pref = random.choice(prefijos)
                suf = random.choice(sufijos)
                nombre = f"{pref} {suf}"
                if (nombre, cat.id) not in equipos_existentes:
                    Equipo.objects.get_or_create(nombre=nombre, categoria=cat, defaults={"activo": True})
                    equipos_existentes.add((nombre, cat.id))
                intentos += 1
            self.stdout.write(f"  {cat.nombre}: {Equipo.objects.filter(categoria=cat).count()} equipos")

    def _poblar_jugadores(self):
        nombres_m = ["Carlos","Luis","Miguel","Jorge","Andrés","Diego","Pablo","Sergio","Fernando",
                      "Alejandro","Ricardo","Javier","Manuel","Roberto","David","Pedro","Juan","Antonio",
                      "Francisco","Rafael","Eduardo","Gustavo","Héctor","Iván","Julián","Leonardo","Marco",
                      "Néstor","Oscar","Rubén","Samuel","Tomás","Ulises","Víctor","Wilson","Xavier",
                      "Yahir","Zacarías","Adán","Benito","César","Daniel","Emilio","Felipe","Alan","Bruno",
                      "Christian","Damián","Elías","Fabián","Gabriel","Humberto","Ismael","Jesús","Kevin",
                      "Lorenzo","Mauricio","Noé","Octavio","Raúl","Saúl","Uriel","Vicente","Abel","Hugo",
                      "Ián","Mateo","Nicolás","Oliver","Santiago","Ángel","Brandon","Cristian","Emmanuel",
                      "Gael","Jared","Luis","Rafael","Diego"]
        nombres_f = ["Ana","Brenda","Carmen","Diana","Elena","Fátima","Gabriela","Helena","Irene","Julia",
                      "Karen","Laura","María","Natalia","Ofelia","Patricia","Raquel","Sofía","Adriana",
                      "Beatriz","Claudia","Daniela","Estefanía","Florencia","Guadalupe","Hilda","Isabel",
                      "Jimena","Karla","Liliana","Mónica","Nancy","Olivia","Pamela","Rebeca","Silvia",
                      "Teresa","Úrsula","Valeria","Wendy","Ximena","Yolanda","Zulema","Alejandra","Berenice"]
        apellidos = ["López","García","Hernández","Martínez","Ramírez","Torres","Flores","Ramos","Gómez",
                      "Díaz","Moreno","Álvarez","Romero","Sánchez","Cruz","Rodríguez","Pérez","Luna","Vega",
                      "Mendoza","Ríos","Ortiz","Delgado","Aguilar","Castro","Mora","Peña","Cabrera","Reyes",
                      "Nava","Serrano","Lara","Guerrero","Sandoval","Ibáñez","Palacios","Medina","Espinoza",
                      "Cortés","Maldonado","Salinas","Pacheco","Valenzuela","Navarro","Carrillo","Rangel",
                      "Quintana","Bautista","Fuentes","Villanueva","Covarrubias","Saucedo","Paredes","Becerra",
                      "Zamora","Tapia","Mejía","Hurtado","Castañeda","Llamas","Herrera","Vargas"]
        posiciones = ["POR", "DEF", "DEF", "DEF", "DEF", "MED", "MED", "MED", "MED", "DEL", "DEL"]
        usados = set()
        random.seed(123)
        for eq in Equipo.objects.filter(activo=True):
            actuales = Jugador.objects.filter(equipo=eq).count()
            if actuales >= 20:
                continue
            # Determinar género
            cat = eq.categoria
            es_femenil = cat.genero and cat.genero.lower() in ("femenino", "femenil")
            pool_nombres = nombres_f if es_femenil else nombres_m
            objetivo = min(26, max(actuales, 20))
            while Jugador.objects.filter(equipo=eq).count() < objetivo:
                nombre = random.choice(pool_nombres)
                apellido = random.choice(apellidos)
                key = (nombre, apellido, eq.id)
                if key in usados:
                    continue
                usados.add(key)
                pos = random.choice(posiciones)
                dorsal_existentes = set(Jugador.objects.filter(equipo=eq).values_list("dorsal", flat=True))
                dorsal = random.randint(1, 99)
                while dorsal in dorsal_existentes:
                    dorsal = random.randint(1, 99)
                Jugador.objects.get_or_create(
                    nombre=nombre, apellido=apellido, equipo=eq,
                    defaults={"posicion": pos, "dorsal": dorsal},
                )

    def _crear_conceptos(self):
        conceptos = [
            ("Venta de Credenciales", "Venta de credenciales de acceso a jugadores", 50.00, True),
            ("Inscripción de Equipo", "Pago de inscripción por equipo por temporada", 500.00, False),
            ("Pago de Horario", "Pago por renta de campo por horario fijo", 200.00, False),
            ("Día Fijo", "Pago por día fijo semanal de juego", 350.00, False),
            ("Multas", "Pago de multas reglamentarias", 100.00, False),
            ("Horario Fijo", "Pago por asignación de horario fijo en el rol", 300.00, False),
        ]
        for nombre, desc, monto, req_jug in conceptos:
            requiere_eq = nombre in ("Inscripción de Equipo", "Horario Fijo")
            obj, created = ConceptoIngreso.objects.get_or_create(
                nombre=nombre,
                defaults={"descripcion": desc, "monto_defecto": monto, "requiere_jugador": req_jug, "requiere_equipo": requiere_eq},
            )
            if not created:
                obj.requiere_jugador = req_jug
                obj.requiere_equipo = requiere_eq
                obj.save()
        self.stdout.write(self.style.SUCCESS("Conceptos OK"))
