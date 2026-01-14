import { Suspense } from "react";
import RepoDetailClient from "./RepoDetailClient";

export default function RepoDetailPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen px-6 py-10 lg:px-12">
          <section className="mx-auto max-w-4xl rounded-3xl border border-ink/10 bg-surface/80 p-8 shadow-soft">
            <p className="text-sm text-ink/70">Loading...</p>
          </section>
        </main>
      }
    >
      <RepoDetailClient />
    </Suspense>
  );
}
