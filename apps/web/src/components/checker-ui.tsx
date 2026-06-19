"use client";

import * as React from "react";
import { Check } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export function CheckerSurface({
  className,
  children,
}: React.ComponentProps<"section">) {
  return (
    <section
      className={cn(
        "rounded-xl border border-border bg-card text-card-foreground shadow-sm",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function CheckerPanel({
  className,
  children,
}: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-muted/35 text-foreground",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SectionHeader({
  label,
  title,
  description,
  action,
  className,
}: {
  label?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between", className)}>
      <div className="min-w-0">
        {label ? (
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
            {label}
          </div>
        ) : null}
        <h2 className="mt-2 text-xl font-semibold text-foreground md:text-2xl">
          {title}
        </h2>
        {description ? (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function MetricTile({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "accent";
}) {
  const toneClass =
    tone === "success"
      ? "bg-[var(--success-bg)] text-[var(--success)]"
      : tone === "warning"
        ? "bg-[var(--warning-bg)] text-[var(--warning)]"
        : tone === "danger"
          ? "bg-[var(--danger-bg)] text-[var(--danger)]"
          : tone === "accent"
            ? "bg-primary/10 text-primary"
            : "bg-muted text-foreground";

  return (
    <div className={cn("rounded-lg border border-border p-3", toneClass)}>
      <div className="text-[11px] font-medium uppercase tracking-[0.14em] opacity-75">
        {label}
      </div>
      <div className="mt-2 text-lg font-semibold">{value}</div>
    </div>
  );
}

export function StatusBadge({
  children,
  tone = "neutral",
  className,
}: {
  children: React.ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "accent";
  className?: string;
}) {
  return (
    <Badge
      variant={tone === "danger" ? "destructive" : tone === "neutral" ? "outline" : "secondary"}
      className={cn(
        "h-auto rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em]",
        tone === "success" && "bg-[var(--success-bg)] text-[var(--success)]",
        tone === "warning" && "bg-[var(--warning-bg)] text-[var(--warning)]",
        tone === "accent" && "bg-primary/10 text-primary",
        className,
      )}
    >
      {children}
    </Badge>
  );
}

export type SelectOption<T extends string> = {
  value: T;
  label: React.ReactNode;
};

export function SelectField<T extends string>({
  label,
  description,
  value,
  onValueChange,
  options,
  className,
  triggerClassName,
}: {
  label: string;
  description?: React.ReactNode;
  value: T;
  onValueChange: (value: T) => void;
  options: Array<SelectOption<T>>;
  className?: string;
  triggerClassName?: string;
}) {
  return (
    <Field className={className}>
      <FieldLabel className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </FieldLabel>
      <Select
        items={options}
        value={value}
        onValueChange={(next) => {
          if (typeof next === "string") onValueChange(next as T);
        }}
      >
        <SelectTrigger className={cn("h-10 w-full rounded-lg bg-background", triggerClassName)}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent align="start">
          <SelectGroup>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
      {description ? <FieldDescription>{description}</FieldDescription> : null}
    </Field>
  );
}

export function CheckboxChip({
  label,
  checked,
  onCheckedChange,
  className,
}: {
  label: React.ReactNode;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={checked}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "inline-flex min-h-10 items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:border-primary/40 aria-pressed:bg-primary/10 aria-pressed:text-foreground",
        className,
      )}
    >
      <span
        className={cn(
          "grid size-4 place-items-center rounded border border-input bg-background text-primary-foreground",
          checked && "border-primary bg-primary",
        )}
        aria-hidden="true"
      >
        {checked ? <Check className="size-3" /> : null}
      </span>
      <span className="leading-5">{label}</span>
    </button>
  );
}

export function CheckboxField({
  id,
  label,
  checked,
  onCheckedChange,
}: {
  id: string;
  label: React.ReactNode;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <Field orientation="horizontal" className="items-center rounded-lg border border-border bg-background px-3 py-2">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(next) => onCheckedChange(next === true)}
      />
      <FieldLabel htmlFor={id} className="text-sm text-foreground">
        {label}
      </FieldLabel>
    </Field>
  );
}

export function SwitchRow({
  id,
  label,
  description,
  checked,
  onCheckedChange,
}: {
  id: string;
  label: React.ReactNode;
  description?: React.ReactNode;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <label
      htmlFor={id}
      className="flex min-h-12 items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2 text-sm"
    >
      <span>
        <span className="block font-medium text-foreground">{label}</span>
        {description ? (
          <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">
            {description}
          </span>
        ) : null}
      </span>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} />
    </label>
  );
}

export function FormGrid({ className, ...props }: React.ComponentProps<typeof FieldGroup>) {
  return <FieldGroup className={cn("grid gap-4", className)} {...props} />;
}

export { Button };
