import React, { createContext, useContext, useMemo, useState } from 'react';

export interface CartItem { productId: string; name: string; price: number; size: string; quantity: number; }
interface CartValue {
  items: CartItem[]; count: number; subtotal: number;
  lastAdded: { name: string; size: string; at: number } | null;
  add(item: CartItem): void; remove(productId: string, size: string): void; clear(): void;
}
const CartContext = createContext<CartValue | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);
  const [lastAdded, setLastAdded] = useState<{ name: string; size: string; at: number } | null>(null);
  const value = useMemo<CartValue>(() => ({
    items,
    count: items.reduce((n, i) => n + i.quantity, 0),
    subtotal: items.reduce((s, i) => s + i.price * i.quantity, 0),
    lastAdded,
    add: (item) => {
      setLastAdded({ name: item.name, size: item.size, at: Date.now() });
      setItems(prev => {
        const hit = prev.find(i => i.productId === item.productId && i.size === item.size);
        return hit ? prev.map(i => (i === hit ? { ...i, quantity: i.quantity + item.quantity } : i)) : [...prev, item];
      });
    },
    remove: (productId, size) => setItems(prev => prev.filter(i => !(i.productId === productId && i.size === size))),
    clear: () => setItems([]),
  }), [items, lastAdded]);
  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error('useCart must be used inside <CartProvider>');
  return ctx;
}

