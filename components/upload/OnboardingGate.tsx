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
  const baseUrl =
    process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000";

  try {
    const res = await fetch(
      `${baseUrl}/api/onboarding/status?business_id=${businessId}`,
      { cache: "no-store" }
    );

    if (!res.ok) {
      return false;
    }

    const data: OnboardingStatusResponse = await res.json();
    return data.onboarding_complete === true;
  } catch {
    // Network error or any other failure → treat as incomplete (safe default)
    return false;
  }
}

export default async function OnboardingGate({ children }: OnboardingGateProps) {
  const isComplete = await getOnboardingStatus();

  if (!isComplete) {
    return <OnboardingRequiredBanner />;
  }

  return <>{children}</>;
}
