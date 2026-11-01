"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { PanelIntro, PanelShell } from "@/components/settings/panel-chrome";

interface Profile {
  name: string;
  industry: string;
  stage: string;
  mission: string;
  vision: string;
  headcount: number | null;
  website: string;
}

const empty: Profile = {
  name: "",
  industry: "",
  stage: "",
  mission: "",
  vision: "",
  headcount: null,
  website: "",
};

export function CompanyProfilePanel() {
  const [profile, setProfile] = useState<Profile>(empty);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [interviewId, setInterviewId] = useState<string | null>(null);
  const [opening, setOpening] = useState("");
  const [message, setMessage] = useState("");
  const [question, setQuestion] = useState<string | null>(null);
  const [draftSummary, setDraftSummary] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api<{ profile: Profile }>("/company-profile");
        setProfile({ ...empty, ...data.profile });
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Failed to load profile");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function save() {
    setBusy(true);
    try {
      await api("/company-profile", { method: "PUT", body: JSON.stringify(profile) });
      toast.success("Company profile saved.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function startInterview() {
    setBusy(true);
    try {
      const data = await api<{ session_id: string; opening: string }>(
        "/onboard/interview/start",
        { method: "POST", body: "{}" },
      );
      setInterviewId(data.session_id);
      setOpening(data.opening);
      setQuestion(null);
      setDraftSummary(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start interview");
    } finally {
      setBusy(false);
    }
  }

  async function sendInterview(forceDraft = false) {
    if (!interviewId || (!message.trim() && !forceDraft)) return;
    setBusy(true);
    try {
      const data = await api<{
        type: string;
        question?: string;
        profile?: Profile;
        summary?: string;
      }>("/onboard/interview/message", {
        method: "POST",
        body: JSON.stringify({
          session_id: interviewId,
          message: message || "Please draft from what you have.",
          force_draft: forceDraft,
        }),
      });
      setMessage("");
      if (data.type === "question") {
        setQuestion(data.question ?? null);
        setDraftSummary(null);
      } else if (data.type === "draft" && data.profile) {
        setProfile({ ...empty, ...data.profile });
        setDraftSummary(data.summary || "Draft ready — review and commit.");
        setQuestion(null);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Interview failed");
    } finally {
      setBusy(false);
    }
  }

  async function commitInterview() {
    if (!interviewId) return;
    setBusy(true);
    try {
      await api("/onboard/interview/commit", {
        method: "POST",
        body: JSON.stringify({ session_id: interviewId, profile }),
      });
      toast.success("Profile committed.");
      setInterviewId(null);
      setOpening("");
      setQuestion(null);
      setDraftSummary(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Commit failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PanelShell>
      <PanelIntro
        title="Company profile"
        description="Workspace-level context injected into every Executive turn."
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Name</span>
                <Input
                  value={profile.name}
                  onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Website</span>
                <Input
                  value={profile.website}
                  onChange={(e) => setProfile({ ...profile, website: e.target.value })}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Industry</span>
                <Input
                  value={profile.industry}
                  onChange={(e) => setProfile({ ...profile, industry: e.target.value })}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Stage</span>
                <Input
                  value={profile.stage}
                  onChange={(e) => setProfile({ ...profile, stage: e.target.value })}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-muted-foreground">Headcount</span>
                <Input
                  type="number"
                  value={profile.headcount ?? ""}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      headcount: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </label>
            </div>
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">Mission</span>
              <Textarea
                rows={3}
                value={profile.mission}
                onChange={(e) => setProfile({ ...profile, mission: e.target.value })}
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">Vision</span>
              <Textarea
                rows={2}
                value={profile.vision}
                onChange={(e) => setProfile({ ...profile, vision: e.target.value })}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button disabled={busy} onClick={() => void save()}>
                Save profile
              </Button>
              <Button variant="outline" disabled={busy} onClick={() => void startInterview()}>
                Start interview
              </Button>
            </div>

            {interviewId && (
              <div className="space-y-3 rounded-xl border border-black/5 bg-white p-4 dark:border-white/10 dark:bg-card">
                <p className="text-sm text-muted-foreground">{opening}</p>
                {question && <p className="text-sm font-medium">{question}</p>}
                {draftSummary && <p className="text-sm text-emerald-700">{draftSummary}</p>}
                <Textarea
                  rows={3}
                  value={message}
                  placeholder="Your answer…"
                  onChange={(e) => setMessage(e.target.value)}
                />
                <div className="flex flex-wrap gap-2">
                  <Button disabled={busy} onClick={() => void sendInterview(false)}>
                    Send
                  </Button>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => void sendInterview(true)}
                  >
                    Force draft
                  </Button>
                  <Button disabled={busy || !profile.name} onClick={() => void commitInterview()}>
                    Commit draft
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </PanelShell>
  );
}
