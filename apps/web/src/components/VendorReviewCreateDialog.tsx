"use client";

import { useEffect, useRef, useState } from "react";
import {
  BriefcaseBusiness,
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
import { CheckboxChip, SelectField, SwitchRow } from "@/components/checker-ui";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

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
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-md"
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
              className="grid max-h-[92vh] w-full max-w-5xl overflow-hidden rounded-xl border border-border bg-card text-left text-card-foreground shadow-2xl lg:grid-cols-[0.82fr_1.18fr]"
              onClick={(event) => event.stopPropagation()}
            >
              <h2 id="vendor-review-create-title" className="sr-only">New Vendor Review</h2>
              <aside
                className="hidden min-h-[560px] flex-col justify-between border-r border-border bg-muted/35 px-8 py-8 lg:flex"
              >
                <div>
                  <div
                    className="mb-8 inline-flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-background text-primary"
                  >
                    <ShieldCheck className="h-5 w-5" />
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.32em] text-primary">
                    Checker intake
                  </div>
                  <h2 className="mt-5 max-w-xs text-4xl font-semibold leading-[1.02] text-foreground">
                    New Vendor Review
                  </h2>
                </div>

                <div className="grid gap-3">
                  <div className="flex items-start gap-3 rounded-lg border border-border bg-background px-4 py-3">
                    <BriefcaseBusiness className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div>
                      <div className="text-sm font-medium text-foreground">Vendor context</div>
                      <div className="mt-1 text-xs leading-5 text-muted-foreground">Name, use case, data profile, criticality.</div>
                    </div>
                  </div>
                  <div className="flex items-start gap-3 rounded-lg border border-border bg-background px-4 py-3">
                    <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div>
                      <div className="text-sm font-medium text-foreground">Workspace ready</div>
                      <div className="mt-1 text-xs leading-5 text-muted-foreground">Documents, criteria, review run, Approval Pack.</div>
                    </div>
                  </div>
                </div>
              </aside>

              <div className="overflow-y-auto px-5 py-5 sm:px-8 sm:py-7">
                <div className="mb-7 flex items-start justify-between gap-6 lg:hidden">
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.28em] text-primary">Checker intake</div>
                    <h2 id="vendor-review-create-title-mobile" className="mt-3 text-3xl font-semibold text-foreground">
                      New Vendor Review
                    </h2>
                  </div>
                  <Button
                    type="button"
                    onClick={close}
                    variant="ghost"
                    size="icon-lg"
                    className="shrink-0 text-muted-foreground hover:text-foreground"
                    aria-label="Close"
                  >
                    <X className="h-5 w-5" />
                  </Button>
                </div>

                <div className="hidden items-start justify-end lg:flex">
                  <Button
                    type="button"
                    onClick={close}
                    variant="ghost"
                    size="icon-lg"
                    className="shrink-0 text-muted-foreground hover:text-foreground"
                    aria-label="Close"
                  >
                    <X className="h-5 w-5" />
                  </Button>
                </div>

                <div className="grid gap-5">
                  <label className="block">
                    <span className="mb-2 block text-xs uppercase tracking-[0.18em] text-muted-foreground">
                      Vendor
                    </span>
                    <Input
                      ref={vendorInputRef}
                      value={vendorName}
                      onChange={(event) => setVendorName(event.target.value)}
                      placeholder="ITG"
                      className="h-12 rounded-lg bg-background px-4 text-base"
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && canCreate) void handleCreate();
                      }}
                    />
                  </label>

                  <label className="block">
                    <span className="mb-2 block text-xs uppercase tracking-[0.18em] text-muted-foreground">
                      Intended use case
                    </span>
                    <Textarea
                      value={intendedUseCase}
                      onChange={(event) => setIntendedUseCase(event.target.value)}
                      placeholder="AI chatbot for customer support"
                      rows={4}
                      className="min-h-28 resize-none rounded-lg bg-background px-4 py-3 text-base leading-6"
                    />
                  </label>

                  <div className="grid gap-4 md:grid-cols-[0.78fr_1.22fr]">
                    <SwitchRow
                      id="create-shares-personal-data"
                      label="Personal data"
                      description={sharesPersonalData ? "Vendor receives personal data." : "No personal data in scope."}
                      checked={sharesPersonalData}
                      onCheckedChange={setPersonalData}
                    />

                    <div>
                      <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Business criticality
                      </div>
                      <ToggleGroup
                        value={[businessCriticality]}
                        onValueChange={(values) => {
                          const next = values.at(-1) as BusinessCriticality | undefined;
                          if (next) setBusinessCriticality(next);
                        }}
                        className="grid w-full grid-cols-1 items-stretch gap-2 sm:grid-cols-3"
                      >
                        {CRITICALITY_OPTIONS.map((option) => {
                          const selected = businessCriticality === option.value;
                          return (
                            <ToggleGroupItem
                              key={option.value}
                              value={option.value}
                              variant="outline"
                              className="h-auto min-h-[88px] w-full flex-col items-start justify-start whitespace-normal rounded-lg bg-background p-3 text-left text-muted-foreground aria-pressed:border-primary/50 aria-pressed:bg-primary/10 aria-pressed:text-foreground"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-sm font-medium">{option.label}</span>
                                {selected ? <ShieldAlert className="h-4 w-4 text-primary" /> : null}
                              </div>
                              <div className="mt-2 text-xs leading-5 text-muted-foreground">{option.copy}</div>
                            </ToggleGroupItem>
                          );
                        })}
                      </ToggleGroup>
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-[1fr_0.72fr]">
                    <div>
                      <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        Data profile
                      </div>
                      <ToggleGroup
                        multiple
                        disabled={!sharesPersonalData}
                        value={sharesPersonalData ? dataTypes.filter((item) => item !== "no_personal_data") : []}
                        onValueChange={(values) => {
                          if (values.length) setDataTypes(values);
                        }}
                        className="grid w-full grid-cols-2 items-stretch gap-2 sm:grid-cols-3"
                      >
                        {DATA_TYPE_OPTIONS.map((option) => {
                          const selected = dataTypes.includes(option.value) && sharesPersonalData;
                          return (
                            <ToggleGroupItem
                              key={option.value}
                              value={option.value}
                              variant="outline"
                              className="h-auto min-h-11 w-full whitespace-normal rounded-lg bg-background px-3 py-2 text-center text-sm text-muted-foreground aria-pressed:border-primary/50 aria-pressed:bg-primary/10 aria-pressed:text-foreground"
                            >
                              <span className="leading-5">{option.label}</span>
                              {selected ? <span className="sr-only">selected</span> : null}
                            </ToggleGroupItem>
                          );
                        })}
                      </ToggleGroup>
                    </div>

                    <SelectField
                      label="Vendor region"
                      value={vendorRegion}
                      onValueChange={setVendorRegion}
                      options={REGION_OPTIONS}
                      triggerClassName="h-11"
                    />
                  </div>

                  <div className="grid gap-4 md:grid-cols-3">
                    <SwitchRow
                      id="create-processes-eu-data"
                      label="EU personal data"
                      description={processesEuPersonalData ? "EU/EEA data is in scope." : "No EU/EEA data expected."}
                      checked={processesEuPersonalData}
                      onCheckedChange={setProcessesEuPersonalData}
                    />

                    <SwitchRow
                      id="create-transfers-eea-data"
                      label="EEA transfer"
                      description={transfersDataOutsideEea ? "Transfer outside EEA expected." : "No EEA transfer expected."}
                      checked={transfersDataOutsideEea}
                      onCheckedChange={setTransfersDataOutsideEea}
                    />

                    <CheckboxChip
                      label="AI features or model training"
                      checked={hasAiFeatures}
                      onCheckedChange={setHasAiFeatures}
                      className="min-h-[68px] justify-start rounded-lg px-4 py-3"
                    />
                  </div>

                  {error ? (
                    <Alert variant="destructive" className="border-destructive/30 bg-[var(--danger-bg)]">
                      <AlertDescription className="text-[var(--danger)]">{error}</AlertDescription>
                    </Alert>
                  ) : null}

                  <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:items-center sm:justify-end">
                    <Button
                      type="button"
                      onClick={close}
                      disabled={creating}
                      variant="ghost"
                      size="lg"
                      className="h-11 px-5"
                    >
                      Cancel
                    </Button>
                    <Button
                      type="button"
                      onClick={() => void handleCreate()}
                      disabled={creating || !canCreate}
                      size="lg"
                      className="h-11 px-6"
                    >
                      {creating ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <BriefcaseBusiness className="h-4 w-4" />}
                      Create Review
                    </Button>
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
