/**
 * Framework-safe native value setters for React, Vue, and other controlled components
 * Uses native prototype setters to bypass framework virtual DOM tracking
 * Emits proper bubbling events to notify framework state
 */

export interface NativeSetterOptions {
  validateConstraints?: boolean;
  commitEvent?: 'input' | 'change' | 'blur';
}

const DEFAULT_OPTIONS: Required<NativeSetterOptions> = {
  validateConstraints: true,
  commitEvent: 'input',
};

/**
 * Validates constraints on a detached clone before touching the real DOM
 */
function validateInputConstraints(
  element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
  value: string
): { valid: boolean; message?: string } {
  const probe = element.cloneNode(true) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
  probe.value = value;

  if (!probe.checkValidity()) {
    return {
      valid: false,
      message: `Value '${value}' violates native constraints: ${probe.validationMessage}`,
    };
  }
  return { valid: true };
}

/**
 * Gets the native setter from the prototype chain
 * Works around React 18/19 and Vue's property interception
 */
function getNativeSetter(
  element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
): ((value: string) => void) | null {
  const prototype = Object.getPrototypeOf(element);

  // Try element's own prototype first
  const ownDescriptor = Object.getOwnPropertyDescriptor(prototype, 'value');
  if (ownDescriptor?.set) {
    return ownDescriptor.set;
  }

  // Fall back to HTMLInputElement prototype
  const inputDescriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
  if (inputDescriptor?.set) {
    return inputDescriptor.set;
  }

  // Fall back to HTMLTextAreaElement prototype
  const textareaDescriptor = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
  if (textareaDescriptor?.set) {
    return textareaDescriptor.set;
  }

  // Fall back to HTMLSelectElement prototype
  const selectDescriptor = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
  if (selectDescriptor?.set) {
    return selectDescriptor.set;
  }

  return null;
}

/**
 * Sets the native value on an input/textarea/select element
 * Bypasses framework virtual DOM and dispatches proper bubbling events
 */
export function setNativeValue(
  element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
  value: string | number | boolean,
  options: NativeSetterOptions = {}
): void {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const stringValue = String(value);

  // 1. Validate constraints on a detached clone probe
  if (opts.validateConstraints) {
    const validation = validateInputConstraints(element, stringValue);
    if (!validation.valid) {
      throw new Error(validation.message);
    }
  }

  // 2. Locate native prototype setter
  const nativeSetter = getNativeSetter(element);

  if (nativeSetter) {
    // Use native setter to bypass React/Vue property tracking
    nativeSetter.call(element, stringValue);
  } else {
    // Fallback: direct assignment
    element.value = stringValue;
  }

  // 3. Dispatch bubbling events for framework listeners
  // React 18+ listens for 'input' and 'change' with bubbles: true
  element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));

  if (opts.commitEvent === 'change' || opts.commitEvent === 'input') {
    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
  }

  if (opts.commitEvent === 'blur') {
    element.dispatchEvent(new FocusEvent('blur', { bubbles: false, cancelable: true }));
  }
}

/**
 * Sets value for native select element
 */
export function setNativeSelectValue(
  select: HTMLSelectElement,
  value: string,
  options: NativeSetterOptions = {}
): boolean {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  // Find and select the option
  const option = Array.from(select.options).find(
    (opt) => opt.value === value || opt.textContent === value
  );

  if (!option) {
    return false;
  }

  if (option.disabled) {
    throw new Error(`Option '${value}' is disabled`);
  }

  option.selected = true;

  // Use native setter for the select element
  const nativeSetter = getNativeSetter(select);
  if (nativeSetter) {
    nativeSetter.call(select, value);
  } else {
    select.value = value;
  }

  // Dispatch events
  select.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
  select.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));

  return true;
}

/**
 * Sets checkbox/radio state natively
 */
export function setNativeCheckboxState(
  element: HTMLInputElement,
  checked: boolean,
  options: NativeSetterOptions = {}
): void {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  if (element.type !== 'checkbox' && element.type !== 'radio') {
    throw new Error('Element is not a checkbox or radio');
  }

  if (element.checked !== checked) {
    // Use native setter for checked property
    const nativeCheckedSetter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'checked'
    )?.set;

    if (nativeCheckedSetter) {
      nativeCheckedSetter.call(element, checked);
    } else {
      element.checked = checked;
    }

    // Dispatch events
    element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
  }
}

/**
 * Verifies the value was retained after render
 */
export function verifyValueRetained(
  element: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
  expectedValue: string
): { retained: boolean; actualValue: string } {
  const actualValue = element.value;
  return {
    retained: actualValue === expectedValue,
    actualValue,
  };
}