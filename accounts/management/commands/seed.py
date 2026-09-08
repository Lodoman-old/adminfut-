from django.core.management.base import BaseCommand
from accounts.models import Rol, Usuario
from finance.models import ConceptoIngreso


class Command(BaseCommand):
    help = "Inicializa datos básicos del sistema"

    def handle(self, *args, **options):
        self._crear_roles()
        self._crear_conceptos()
        self.stdout.write(self.style.SUCCESS("Seed completado — solo roles, admin y conceptos financieros"))

    def _crear_roles(self):
        from accounts.models import get_permisos_flat
        flat = get_permisos_flat()
        admin_permisos = {key: True for key, _, _, _, _ in flat}
        admin_rol, _ = Rol.objects.get_or_create(nombre="Administrador", defaults={"permisos": admin_permisos})
        op_permisos = dict(admin_permisos)
        op_permisos.update({
            "gestion_roles": False,
            "gestion_usuarios": False,
            "gestion_suspensiones": False,
            "temporada_movimientos": False,
            "gestion_jugadores_heredados": False,
        })
        Rol.objects.get_or_create(nombre="Operador", defaults={"permisos": op_permisos})
        inv_permisos = {key: False for key, _, _, _, _ in flat}
        inv_permisos.update({"ver_finanzas": False})
        Rol.objects.get_or_create(nombre="Invitado", defaults={"permisos": inv_permisos})
        arb_permisos = {key: False for key, _, _, _, _ in flat}
        arb_permisos.update({"partido_cedula": True})
        Rol.objects.get_or_create(nombre="Arbitro", defaults={"permisos": arb_permisos})
        rep_permisos = {key: False for key, _, _, _, _ in flat}
        rep_permisos.update({"jugador_crear": True, "reporte_semanal": True})
        Rol.objects.get_or_create(nombre="Representante Equipo", defaults={"permisos": rep_permisos})

        # Asegurar que los roles ya existentes tengan todos los permisos nuevos
        # (get_or_create no actualiza roles creados con una versión anterior del seed)
        rol_descriptions = {
            "Administrador": admin_permisos,
            "Operador": op_permisos,
            "Invitado": inv_permisos,
            "Arbitro": arb_permisos,
            "Representante Equipo": rep_permisos,
        }
        for rol in Rol.objects.all():
            defaults = rol_descriptions.get(rol.nombre)
            if not defaults:
                continue
            permisos = dict(rol.permisos or {})
            changed = False
            for key, default in defaults.items():
                if key not in permisos:
                    permisos[key] = default
                    changed = True
            if changed:
                rol.permisos = permisos
                rol.save(update_fields=["permisos"])

        admin_user, created = Usuario.objects.get_or_create(
            username="admin",
            defaults={
                "rol": admin_rol,
                "is_superuser": True,
                "is_staff": True,
            },
        )
        if created:
            admin_user.set_password("admin123")
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Usuario admin creado (admin / admin123)"))
        else:
            admin_user.rol = admin_rol
            admin_user.save()
        self.stdout.write(self.style.SUCCESS("Roles OK"))

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
