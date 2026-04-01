"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { destroyBrowserSession } from "@/lib/api/auth";

import { Button } from "../ui/button";

export function LogoutButton() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <Button
      onClick={() => {
        startTransition(() => {
          void destroyBrowserSession().then(() => {
            router.replace("/login");
            router.refresh();
          });
        });
      }}
      variant="ghost"
    >
      {isPending ? "Signing out..." : "Sign out"}
    </Button>
  );
}
