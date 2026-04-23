import AuditTable, { AuditRow } from "@/components/AuditTable";

// Datos de ejemplo — en producción vienen del endpoint FastAPI /api/audit
const mockRows: AuditRow[] = [
  {
    module: "Conciliación de Caja",
    raw_result: "Discrepancia detectada: -$150.00 MXN vs Ticket POS.",
    copilot_phrase:
      "Hay una fuga en el flujo de efectivo. Los tickets marcados no coinciden con el depósito reportado.",
    archetype: "Operative Genius",
  },
  {
    module: "Gasto Operativo",
    raw_result: "Incremento del 12% en compra de leche deslactosada.",
    copilot_phrase:
      "Tu costo de insumos está subiendo más rápido que tus ventas. Revisa el desperdicio en barra.",
    archetype: "Product Purist",
  },
  {
    module: "Salud del Negocio",
    raw_result: "Margen de utilidad neta: 18%.",
    copilot_phrase:
      "Eres eficiente, pero la inconsistencia en extracciones de espresso está afectando tu recompra.",
    archetype: "Operative Genius",
  },
];

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-zinc-900 px-6 py-10 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <p className="text-emerald-400 text-xs tracking-widest uppercase mb-1">Copiloto Financiero</p>
        <h1 className="text-2xl font-semibold text-zinc-100">Reporte de Auditoría</h1>
        <p className="text-zinc-500 text-sm mt-1">Última actualización: hoy · 3 módulos analizados</p>
      </div>

      {/* Tabla principal */}
      <AuditTable rows={mockRows} />

      {/* Footer hint */}
      <p className="text-zinc-600 text-xs mt-6 text-center">
        Los insights son generados por agentes IA según tu arquetipo de operación.
      </p>
    </div>
  );
}
