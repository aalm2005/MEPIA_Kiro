import OnboardingGate from "@/components/upload/OnboardingGate";
import UploadForm from "@/components/upload/UploadForm";

export default function UploadPage() {
  return (
    <main className="min-h-screen bg-canvas px-6 py-12">
      <div className="max-w-3xl mx-auto">
        <OnboardingGate>
          <UploadForm />
        </OnboardingGate>
      </div>
    </main>
  );
}
