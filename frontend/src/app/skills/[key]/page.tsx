"use client";
import { use } from "react";
import AssetDetail from "@/components/assets/AssetDetail";
export default function SkillPage({ params }: { params: Promise<{ key: string }> }) { return <AssetDetail kind="skill" keyName={use(params).key} />; }
