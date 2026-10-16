import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  setNativeValue,
  setNativeSelectValue,
  setNativeCheckboxState,
  verifyValueRetained,
} from './native-setter';

describe('native-setter', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('fires input and change events and keeps the value on text input', () => {
    const input = document.createElement('input');
    input.type = 'text';
    document.body.appendChild(input);

    const inputEvents: Event[] = [];
    const changeEvents: Event[] = [];
    input.addEventListener('input', (e) => inputEvents.push(e));
    input.addEventListener('change', (e) => changeEvents.push(e));

    setNativeValue(input, 'hello world');

    expect(input.value).toBe('hello world');
    expect(inputEvents.length).toBe(1);
    expect(inputEvents[0].bubbles).toBe(true);
    expect(changeEvents.length).toBe(1);
    expect(changeEvents[0].bubbles).toBe(true);

    const verification = verifyValueRetained(input, 'hello world');
    expect(verification.retained).toBe(true);
    expect(verification.actualValue).toBe('hello world');
  });

  it('fires blur event when commitEvent is blur', () => {
    const input = document.createElement('input');
    document.body.appendChild(input);

    const blurSpy = vi.fn();
    input.addEventListener('blur', blurSpy);

    setNativeValue(input, 'test-val', { commitEvent: 'blur' });

    expect(input.value).toBe('test-val');
    expect(blurSpy).toHaveBeenCalledTimes(1);
  });

  it('throws on constraint violation when validateConstraints is enabled', () => {
    const input = document.createElement('input');
    input.type = 'number';
    input.max = '10';
    document.body.appendChild(input);

    expect(() => {
      setNativeValue(input, '999', { validateConstraints: true });
    }).toThrow(/violates native constraints/);
  });

  it('sets select value and dispatches input and change events', () => {
    const select = document.createElement('select');
    const opt1 = document.createElement('option');
    opt1.value = 'a';
    opt1.textContent = 'Alpha';
    const opt2 = document.createElement('option');
    opt2.value = 'b';
    opt2.textContent = 'Beta';
    select.appendChild(opt1);
    select.appendChild(opt2);
    document.body.appendChild(select);

    const changeSpy = vi.fn();
    select.addEventListener('change', changeSpy);

    const ok = setNativeSelectValue(select, 'b');
    expect(ok).toBe(true);
    expect(select.value).toBe('b');
    expect(changeSpy).toHaveBeenCalledTimes(1);
  });

  it('sets checkbox state and dispatches input and change events', () => {
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = false;
    document.body.appendChild(checkbox);

    const changeSpy = vi.fn();
    checkbox.addEventListener('change', changeSpy);

    setNativeCheckboxState(checkbox, true);
    expect(checkbox.checked).toBe(true);
    expect(changeSpy).toHaveBeenCalledTimes(1);
  });
});

