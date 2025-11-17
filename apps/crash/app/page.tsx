"use client"

import CrashGameArea from "@/components/crash/CrashGameArea";

export default function Page() {
  return (
    <main className="min-h-screen bg-[#181A20] flex flex-col items-center py-6">
      <div className="w-full max-w-5xl">
        <CrashGameArea />
      </div>
    </main>
  );
}
