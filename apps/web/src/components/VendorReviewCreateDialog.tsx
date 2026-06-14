"use client";

import { useEffect, useRef, useState } from "react";
import {
  BriefcaseBusiness,
  Check,
  Database,
  Globe2,
  LoaderCircle,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

import {
  createVendorReview,
  type BusinessCriticality,
  type CreateProjectResponse,
  type VendorRegion,
} from "@/lib/uploadApi";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (project: CreateProjectResponse) => void;
};

const CRITICALITY_OPTIONS: Array<{
  value: BusinessCriticality;
  label: string;
  copy: string;
}> = [
  { value: "low", label: "Low", copy: "Internal or low operational reliance." },
  { value: "medium", label: "Medium", copy: "Business workflow dependency." },
  { value: "high", label: "High", copy: "Critical service or sensitive data exposure." },
];

const DATA_TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "customer_personal_data", label: "Customer" },
  { value: "employee_personal_data", label: "Employee" },
  { value: "support_content", label: "Support content" },
  { value: "account_contact_data", label: "Account/contact" },
  { value: "usage_data", label: "Usage data" },
  { value: "sensitive_personal_data", label: "Sensitive" },
];

const REGION_OPTIONS: Array<{ value: VendorRegion; label: string }> = [
  { value: "US", label: "United States" },
  { value: "EU_EEA", label: "EU / EEA" },
  { value: "UK", label: "United Kingdom" },
  { value: "OTHER", label: "Other / global" },
  { value: "UNKNOWN", label: "Unknown" },
];

const CUSTOMER_DATA_TYPES = new Set(["customer_personal_data", "support_content", "account_contact_data", "usage_data"]);

export default function VendorReviewCreateDialog({ open, onOpenChange, onCreated }: Props) {
  const [creating, setCreating] = useState(false);
  const [vendorName, setVendorName] = useState("");
  const [intendedUseCase, setIntendedUseCase] = useState("");
  const [sharesPersonalData, setSharesPersonalData] = useState(true);
  const [businessCriticality, setBusinessCriticality] = useState<BusinessCriticality>("medium");
  const [dataTypes, setDataTypes] = useState<string[]>(["customer_personal_data"]);
  const [vendorRegion, setVendorRegion] = useState<VendorRegion>("US");
  const [processesEuPersonalData, setProcessesEuPersonalData] = useState(true);
  const [transfersDataOutsideEea, setTransfersDataOutsideEea] = useState(true);
  const [hasAiFeatures, setHasAiFeatures] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const vendorInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => vendorInputRef.current?.focus(), 80);
    return () => clearTimeout(timer);
  }, [open]);

  function reset() {
    setVendorName("");
    setIntendedUseCase("");
    setSharesPersonalData(true);
    setBusinessCriticality("medium");
    setDataTypes(["customer_personal_data"]);
    setVendorRegion("US");
    setProcessesEuPersonalData(true);
    setTransfersDataOutsideEea(true);
    setHasAiFeatures(false);
    setError(null);
  }

  function close() {
    if (creating) return;
    onOpenChange(false);
  }

  async function handleCreate() {
    if (creating || !vendorName.trim() || !intendedUseCase.trim() || !dataTypes.length || !vendorRegion) return;
    setCreating(true);
    setError(null);
    try {
      const selectedDataTypes = sharesPersonalData ? dataTypes : ["no_personal_data"];
      const project = await createVendorReview({
        vendor_name: vendorName.trim(),
        intended_use_case: intendedUseCase.trim(),
        shares_personal_data: sharesPersonalData,
        shares_customer_data: sharesPersonalData && selectedDataTypes.some((item) => CUSTOMER_DATA_TYPES.has(item)),
        shares_employee_data: sharesPersonalData && selectedDataTypes.includes("employee_personal_data"),
        shares_sensitive_data: sharesPersonalData && selectedDataTypes.includes("sensitive_personal_data"),
        has_ai_features: hasAiFeatures,
        business_criticality: businessCriticality,
        data_types: selectedDataTypes,
        vendor_region: vendorRegion,
        processes_eu_personal_data: processesEuPersonalData,
        transfers_data_outside_eea: transfersDataOutsideEea,
        name: `${vendorName.trim()} Vendor Review`,
      });
      reset();
      onCreated(project);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Could not create review.");
    } finally {
      setCreating(false);
    }
  }

  function toggleDataType(value: string) {
    setDataTypes((current) => {
      const next = current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
      return next.length ? next : current;
    });
  }

  function setPersonalData(value: boolean) {
    setSharesPersonalData(value);
    if (!value) {
      setDataTypes(["no_personal_data"]);
      setProcessesEuPersonalData(false);
      setTransfersDataOutsideEea(false);
      return;
    }
    if (dataTypes.includes("no_personal_data")) {
      setDataTypes(["customer_personal_data"]);
      setProcessesEuPersonalData(true);
      setTransfersDataOutsideEea(true);
    }
  }

  const canCreate = vendorName.trim().length > 0 && intendedUseCase.trim().length > 0 && dataTypes.length > 0 && !!vendorRegion;

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="vendor-review-create-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-40 backdrop-blur-md"
            style={{ background: "rgba(0,0,0,0.58)" }}
            onClick={close}
          />
          <motion.div
            key="vendor-review-create-dialog"
            initial={{ opacity: 0, scale: 0.97, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 10 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
            onClick={close}
          >
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="vendor-review-create-title"
              className="grid max-h-[92vh] w-full max-w-5xl overflow-hidden text-left shadow-2xl lg:grid-cols-[0.82fr_1.18fr]"
              style={{ background: "var(--bg)", border: "1px solid var(--line)" }}
              onClick={(event) => event.stopPropagation()}
            >
              <aside
                className="hidden min-h-[560px] flex-col justify-between border-r px-8 py-8 lg:flex"
                style={{ borderColor: "var(--line)", background: "var(--bg-1)" }}
              >
                <div>
                  <div
                    className="mb-8 inline-flex h-11 w-11 items-center justify-center border"
                    style={{ borderColor: "var(--line)", background: "var(--bg)" }}
                  >
                    <ShieldCheck className="h-5 w-5" style={{ color: "var(--accent)" }} />
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.32em]" style={{ color: "var(--accent)" }}>
                    Checker intake
                  </div>
                  <h2 id="vendor-review-create-title" className="mt-5 max-w-xs text-4xl font-semibold leading-[1.02]" style={{ color: "var(--text)" }}>
                    New Vendor Review
                  </h2>
                </div>

                <div className="space-y-3">
                  <div className="flex items-start gap-3 border px-4 py-3" style={{ borderColor: "var(--line)", background: "var(--bg)" }}>
                    <BriefcaseBusiness className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--text-3)" }} />
                    <div>
                      <div className="text-sm font-medium" style={{ color: "var(--text)" }}>Vendor context</div>
                      <div className="mt-1 text-xs leading-5" style={{ color: "var(--text-3)" }}>Name, use case, data profile, criticality.</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-3 border px-4 py-3" style={{ borderColor: "var(--line)", background: "var(--bg)" }}>
                    <Sparkles className="mt-0.5 h-4 w-4 shrink-0" style={{ color: "var(--text-3)" }} />
                    <div>
                      <div className="text-sm font-medium" style={{ color: "var(--text)" }}>Workspace ready</div>
                      <div className="mt-1 text-xs leading-5" style={{ color: "var(--text-3)" }}>Documents, criteria, review run, Approval Pack.</div>
                    </div>
                  </div>
                </div>
              </aside>

              <div className="overflow-y-auto px-5 py-5 sm:px-8 sm:py-7">
                <div className="mb-7 flex items-start justify-between gap-6 lg:hidden">
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.28em]" style={{ color: "var(--accent)" }}>Checker intake</div>
                    <h2 id="vendor-review-create-title-mobile" className="mt-3 text-3xl font-semibold" style={{ color: "var(--text)" }}>
                      New Vendor Review
                    </h2>
                  </div>
                  <button
                    type="button"
                    onClick={close}
                    className="flex h-10 w-10 shrink-0 items-center justify-center transition-colors"
                    style={{ color: "var(--text-3)" }}
                    aria-label="Close"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <div className="hidden items-start justify-end lg:flex">
                  <button
                    type="button"
                    onClick={close}
                    className="flex h-10 w-10 shrink-0 items-center justify-center transition-colors"
                    style={{ color: "var(--text-3)" }}
                    aria-label="Close"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <div className="grid gap-5">
                  <label className="block">
                    <span className="mb-2 block text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
                      Vendor
                    </span>
                    <input
                      ref={vendorInputRef}
                      value={vendorName}
                      onChange={(event) => setVendorName(event.target.value)}
                      placeholder="ITG"
                      className="w-full px-4 py-3.5 text-base outline-none transition-colors"
                      style={{ background: "var(--bg-1)", border: "1px solid var(--line)", color: "var(--text)" }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && canCreate) void handleCreate();
                      }}
                    />
                  </label>

                  <label className="block">
                    <span className="mb-2 block text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
                      Intended use case
                    </span>
                    <textarea
                      value={intendedUseCase}
                      onChange={(event) => setIntendedUseCase(event.target.value)}
                      placeholder="AI chatbot for customer support"
                      rows={4}
                      className="w-full resize-none px-4 py-3.5 text-base leading-7 outline-none transition-colors"
                      style={{ background: "var(--bg-1)", border: "1px solid var(--line)", color: "var(--text)" }}
                    />
                  </label>

                  <div className="grid gap-4 md:grid-cols-[0.78fr_1.22fr]">
                    <div>
                      <div className="mb-2 text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
                        Personal data
                      </div>
                      <div className="grid grid-cols-2 border" style={{ borderColor: "var(--line)" }}>
                        {[true, false].map((value) => {
                          const selected = sharesPersonalData === value;
                          return (
                            <button
                              key={String(value)}
                              type="button"
                              onClick={() => setPersonalData(value)}
                              className="flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition-colors"
                              style={{
                                background: selected ? "var(--invert)" : "var(--bg-1)",
                                color: selected ? "var(--invert-fg)" : "var(--text-2)",
                                borderRight: value ? "1px solid var(--line)" : undefined,
                              }}
                            >
                              {selected ? <Check className="h-4 w-4" /> : <Database className="h-4 w-4" />}
                              {value ? "Yes" : "No"}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div>
                      <div className="mb-2 text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
                        Business criticality
                      </div>
                      <div className="grid gap-2 sm:grid-cols-3">
                        {CRITICALITY_OPTIONS.map((option) => {
                          const selected = businessCriticality === option.value;
                          return (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() => setBusinessCriticality(option.value)}
                              className="border px-3 py-3 text-left transition-colors"
                              style={{
                                borderColor: selected ? "var(--accent)" : "var(--line)",
                                background: selected ? "var(--bg-2)" : "var(--bg-1)",
                                color: selected ? "var(--text)" : "var(--text-2)",
                              }}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-sm font-medium">{option.label}</span>
                                {selected ? <ShieldAlert className="h-4 w-4" style={{ color: "var(--accent)" }} /> : null}
                              </div>
                              <div className="mt-2 text-xs leading-5" style={{ color: "var(--text-3)" }}>{option.copy}</div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-[1fr_0.72fr]">
                    <div>
                      <div className="mb-2 text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
                        Data profile
                      </div>
                      <div className="grid gap-2 sm:grid-cols-3">
                        {DATA_TYPE_OPTIONS.map((option) => {
                          const selected = dataTypes.includes(option.value) && sharesPersonalData;
                          return (
                            <button
                              key={option.value}
                              type="button"
                              disabled={!sharesPersonalData}
                              onClick={() => toggleDataType(option.value)}
                              className="inline-flex min-h-11 items-center justify-center gap-2 border px-3 py-2 text-sm transition-colors disabled:opacity-45"
                              style={{
                                borderColor: selected ? "var(--accent)" : "var(--line)",
                                background: selected ? "var(--bg-2)" : "var(--bg-1)",
                                color: selected ? "var(--text)" : "var(--text-2)",
                              }}
                            >
                              {selected ? <Check className="h-4 w-4 shrink-0" /> : <Database className="h-4 w-4 shrink-0" />}
                              <span className="text-center leading-5">{option.label}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <label className="block">
                      <span className="mb-2 block text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
                        Vendor region
                      </span>
                      <div className="relative">
                        <Globe2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" style={{ color: "var(--text-3)" }} />
                        <select
                          value={vendorRegion}
                          onChange={(event) => setVendorRegion(event.target.value as VendorRegion)}
                          className="h-11 w-full appearance-none px-9 text-sm outline-none"
                          style={{ background: "var(--bg-1)", border: "1px solid var(--line)", color: "var(--text)" }}
                        >
                          {REGION_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </div>
                    </label>
                  </div>

                  <div className="grid gap-4 md:grid-cols-3">
                    <div>
                      <div className="mb-2 text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
                        EU personal data
                      </div>
                      <div className="grid grid-cols-2 border" style={{ borderColor: "var(--line)" }}>
                        {[true, false].map((value) => {
                          const selected = processesEuPersonalData === value;
                          return (
                            <button
                              key={String(value)}
                              type="button"
                              onClick={() => setProcessesEuPersonalData(value)}
                              className="px-3 py-2.5 text-sm font-medium transition-colors"
                              style={{
                                background: selected ? "var(--invert)" : "var(--bg-1)",
                                color: selected ? "var(--invert-fg)" : "var(--text-2)",
                                borderRight: value ? "1px solid var(--line)" : undefined,
                              }}
                            >
                              {value ? "Yes" : "No"}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div>
                      <div className="mb-2 text-xs uppercase tracking-[0.18em]" style={{ color: "var(--text-3)" }}>
                        EEA transfer
                      </div>
                      <div className="grid grid-cols-2 border" style={{ borderColor: "var(--line)" }}>
                        {[true, false].map((value) => {
                          const selected = transfersDataOutsideEea === value;
                          return (
                            <button
                              key={String(value)}
                              type="button"
                              onClick={() => setTransfersDataOutsideEea(value)}
                              className="px-3 py-2.5 text-sm font-medium transition-colors"
                              style={{
                                background: selected ? "var(--invert)" : "var(--bg-1)",
                                color: selected ? "var(--invert-fg)" : "var(--text-2)",
                                borderRight: value ? "1px solid var(--line)" : undefined,
                              }}
                            >
                              {value ? "Yes" : "No"}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <label className="flex min-h-[68px] items-center gap-3 border px-4 py-3 text-sm" style={{ borderColor: "var(--line)", background: "var(--bg-1)", color: "var(--text-2)" }}>
                      <input
                        type="checkbox"
                        checked={hasAiFeatures}
                        onChange={(event) => setHasAiFeatures(event.target.checked)}
                      />
                      <span>AI features or model training</span>
                    </label>
                  </div>

                  {error ? (
                    <div className="border px-4 py-3 text-sm" style={{ borderColor: "rgba(248,113,113,0.35)", color: "var(--danger)" }}>
                      {error}
                    </div>
                  ) : null}

                  <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:items-center sm:justify-end">
                    <button
                      type="button"
                      onClick={close}
                      disabled={creating}
                      className="px-5 py-3 text-sm transition-colors"
                      style={{ color: "var(--text-2)" }}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleCreate()}
                      disabled={creating || !canCreate}
                      className="inline-flex items-center justify-center gap-2 px-6 py-3 text-sm font-medium transition-opacity hover:opacity-85 disabled:opacity-40"
                      style={{ background: "var(--invert)", color: "var(--invert-fg)" }}
                    >
                      {creating ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <BriefcaseBusiness className="h-4 w-4" />}
                      Create Review
                    </button>
                  </div>
                </div>
              </div>
            </section>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
