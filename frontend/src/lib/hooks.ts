"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, clearToken } from "./api";

interface Result<T> { key: string; data: T | null; error: string | null }

export function useApi<T>(path: string | null) {
  const router = useRouter();
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);  // stable, so callers can poll with it
  const key = `${path}#${tick}`;
  const [res, setRes] = useState<Result<T>>({ key: "", data: null, error: null });

  useEffect(() => {
    if (!path) return;
    let live = true;
    api<T>(path)
      .then((data) => live && setRes({ key, data, error: null }))
      .catch((e: unknown) => {
        if (!live) return;
        if (e instanceof ApiError && e.status === 401) { clearToken(); router.replace("/login"); }
        setRes({ key, data: null, error: e instanceof Error ? e.message : "Request failed" });
      });
    return () => { live = false; };
  }, [path, key, router]);

  return {
    data: res.data,
    error: res.error,
    loading: !!path && res.key !== key,
    reload,
  };
}
