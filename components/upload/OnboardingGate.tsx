import Link from "next/link";
import React from "react";

interface OnboardingGateProps {
  children: React.ReactNode;
}

interface OnboardingStatusResponse {
  onboarding_complete: boolean;
}

function OnboardingRequiredBanner() {
  return (
    <div className="bg-warning-bg border border-warning-border text-warning rounded p-4 flex items-center justify-between">
      <span className="text-sm font-medium">
        Configura tu negocio antes de continuar
      </span>
      <Link
        href="/onboarding"
        className="ml-4 shrink-0 text-sm font-semibold text-warning hover:opacity-80 transition-opacity"
      >
        Configurar negocio →
      </Link>
    </div>
  );
}

async function getOnboardingStatus(): Promise<boolean> {
  const businessId = process.env.NEXT_PUBLIC_BUSINESS_ID;
  const agentsUrl =
    process.env.AGENTS_API_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(
      `${agentsUrl}/business/${businessId}/onboarding/status`,
      { cache: "no-store" }
    );

    if (!res.ok) {
      // 404 = negocio no encontrado en DB → onboarding incompleto
      // Cualquier otro error de red → dejar pasar para no bloquear al usuario
      if (res.status === 404) return false;
      return true; // backend caído → no bloquear
    }

    const data: OnboardingStatusResponse = await res.json();
    return data.onboarding_complete === true;
  } catch {
    // Backend Python no disponible → no bloquear al usuario
    return true;
  }
}

export default async function OnboardingGate({ children }: OnboardingGateProps) {
  const isComplete = await getOnboardingStatus();

  if (!isComplete) {
    return <OnboardingRequiredBanner />;
  }

  return <>{children}</>;
}
