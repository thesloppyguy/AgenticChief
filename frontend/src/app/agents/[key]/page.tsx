"use client";
import { use } from "react";
import AssetDetail from "@/components/assets/AssetDetail";
export default function AgentPage({ params }: { params: Promise<{ key: string }> }) { return <AssetDetail kind="agent" keyName={use(params).key} />; }
