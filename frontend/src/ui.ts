import { ApiFailure } from "./api";
import { h } from "./dom";
import { t } from "./strings";

export function toast(message: string, kind: "ok" | "error" = "ok"): void {
  const region = document.getElementById("toasts");
  if (!region) return;
  const element = h("div", { class: `toast toast-${kind}` }, message);
  region.append(element);
  setTimeout(() => element.remove(), kind === "error" ? 8000 : 4000);
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiFailure ? error.message : t.common.unknownError;
}

/** Runs an action, showing any failure, and disables the button while it runs. */
export async function act(
  button: HTMLButtonElement | null,
  run: () => Promise<void>,
): Promise<void> {
  if (button) button.disabled = true;
  try {
    await run();
  } catch (error) {
    toast(errorMessage(error), "error");
  } finally {
    if (button) button.disabled = false;
  }
}

export function openDialog(dialog: HTMLDialogElement): void {
  document.body.append(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.showModal();
}

export interface Field {
  name: string;
  label: string;
  value?: string;
  type?: "text" | "textarea" | "select";
  options?: { value: string; label: string }[];
  required?: boolean;
  maxlength?: number;
}

/** A small form in a dialog. onSubmit may throw: the message appears in the dialog and it stays open. */
export function formDialog(
  title: string,
  fields: Field[],
  submit: string,
  onSubmit: (values: Record<string, string>) => Promise<void>,
): void {
  const error = h("p", { class: "form-error", role: "alert", hidden: true });
  const inputs = fields.map((field) => {
    const id = `field-${field.name}`;
    let control: HTMLElement;
    if (field.type === "select") {
      control = h(
        "select",
        { id, name: field.name },
        ...(field.options ?? []).map((option) =>
          h(
            "option",
            { value: option.value, selected: option.value === field.value },
            option.label,
          ),
        ),
      );
    } else if (field.type === "textarea") {
      control = h(
        "textarea",
        { id, name: field.name, rows: 3, maxlength: field.maxlength },
        field.value ?? "",
      );
    } else {
      control = h("input", {
        id,
        name: field.name,
        type: "text",
        value: field.value ?? "",
        required: field.required,
        maxlength: field.maxlength,
        autocomplete: "off",
      });
    }
    return h("div", { class: "field" }, h("label", { for: id }, field.label), control);
  });
  const dialog = h("dialog", { class: "dialog dialog-small" });
  const confirm = h("button", { class: "btn btn-primary", type: "submit" }, submit);
  const form = h(
    "form",
    {
      onsubmit: (async (event: Event) => {
        event.preventDefault();
        const values = Object.fromEntries(new FormData(form).entries()) as Record<string, string>;
        confirm.disabled = true;
        error.hidden = true;
        try {
          await onSubmit(values);
          dialog.close();
        } catch (failure) {
          error.textContent = errorMessage(failure);
          error.hidden = false;
        } finally {
          confirm.disabled = false;
        }
      }) as EventListener,
    },
    h("h2", {}, title),
    ...inputs,
    error,
    h(
      "div",
      { class: "dialog-actions" },
      confirm,
      h("button", { class: "btn", type: "button", onclick: () => dialog.close() }, t.common.cancel),
    ),
  );
  dialog.append(form);
  openDialog(dialog);
  const first = dialog.querySelector<HTMLInputElement>("input, select, textarea");
  first?.select?.();
}

export function confirmDialog(
  message: string,
  action: string,
  onConfirm: () => Promise<void>,
): void {
  const dialog = h("dialog", { class: "dialog dialog-small" });
  const button = h("button", { class: "btn btn-danger" }, action);
  button.addEventListener("click", () => {
    void act(button, async () => {
      await onConfirm();
      dialog.close();
    });
  });
  dialog.append(
    h("p", {}, message),
    h(
      "div",
      { class: "dialog-actions" },
      button,
      h("button", { class: "btn", onclick: () => dialog.close() }, t.common.cancel),
    ),
  );
  openDialog(dialog);
}
