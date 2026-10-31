import { type IconNode, createElement as lucideElement } from "lucide";

type Child = Node | string | number | null | undefined | false;
type Attrs = Record<string, string | number | boolean | null | undefined | EventListener>;

/** Builds elements. Text always becomes text nodes, so data from Habbo or imports cannot inject markup. */
export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Attrs = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (typeof value === "function") {
      element.addEventListener(name.replace(/^on/, ""), value);
    } else if (name === "value" && "value" in element) {
      (element as HTMLInputElement).value = String(value);
    } else {
      element.setAttribute(name, value === true ? "" : String(value));
    }
  }
  element.append(...children.filter(isChild).map(asNode));
  return element;
}

function isChild(child: Child): child is Node | string | number {
  return child !== null && child !== undefined && child !== false;
}

function asNode(child: Node | string | number): Node | string {
  return typeof child === "number" ? String(child) : child;
}

export function icon(node: IconNode, size = 16): SVGElement {
  const svg = lucideElement(node);
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("aria-hidden", "true");
  return svg;
}

export function replace(parent: Element, ...children: Child[]): void {
  parent.replaceChildren(...children.filter(isChild).map(asNode));
}

export function debounce<A extends unknown[]>(run: (...args: A) => void, ms: number) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return (...args: A) => {
    clearTimeout(timer);
    timer = setTimeout(() => run(...args), ms);
  };
}
