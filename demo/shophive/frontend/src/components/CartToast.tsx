import React, { useEffect, useState } from 'react';
import { useCart } from '../cart/CartContext';

export function CartToast() {
  const { lastAdded } = useCart();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!lastAdded) return;
    setVisible(true);
    const timer = setTimeout(() => {
      setVisible(false);
    }, 2500);
    return () => clearTimeout(timer);
  }, [lastAdded]);

  if (!visible || !lastAdded) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-6 left-6 z-50 rounded-full bg-gray-900 px-4 py-2.5 text-sm font-medium text-white shadow-lg dark:bg-gray-100 dark:text-gray-900"
    >
      ✓ Added {lastAdded.name} (size {lastAdded.size}) to your cart
    </div>
  );
}

