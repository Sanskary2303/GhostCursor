import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useCart } from '../cart/CartContext';

export function Cart() {
  const navigate = useNavigate();
  const { items, subtotal, remove } = useCart();
  const [promoCode, setPromoCode] = useState('');
  const [appliedPromo, setAppliedPromo] = useState<string | null>(null);
  const [promoError, setPromoError] = useState<string | null>(null);

  const handleApplyPromo = () => {
    if (promoCode.trim().toUpperCase() === 'SAVE20') {
      setAppliedPromo('SAVE20');
      setPromoError(null);
    } else {
      setAppliedPromo(null);
      setPromoError('Unknown code');
    }
  };

  const discount = appliedPromo === 'SAVE20' ? subtotal * 0.2 : 0;
  const discountedSubtotal = subtotal - discount;
  const shipping = subtotal > 75 ? 0 : 8.99;
  const tax = discountedSubtotal * 0.08;
  const total = (subtotal - discount) + shipping + tax;

  if (items.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="text-6xl mb-4">🛒</div>
        <h2 className="text-2xl font-bold mb-2">Your cart is empty</h2>
        <p className="text-gray-600 mb-6">Looks like you haven't added anything yet.</p>
        <Link
          to="/"
          className="inline-block bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700"
        >
          Start Shopping
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">Shopping Cart</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Cart Items */}
        <div className="lg:col-span-2 space-y-4">
          {items.map((item) => (
            <div
              key={`${item.productId}-${item.size}`}
              className="bg-white rounded-xl border border-gray-200 p-4 flex items-center space-x-4"
            >
              <div className="w-24 h-24 bg-gray-100 rounded-lg flex items-center justify-center text-3xl">
                {item.productId === 'air-max-90' ? '🟦' : item.productId === 'jordan-1' ? '🟥' : '👟'}
              </div>
              <div className="flex-1">
                <h3 data-ghost-id={`cart.item.${item.productId}.title`} className="font-semibold">
                  {item.name}
                </h3>
                <p className="text-sm text-gray-600">Size: US {item.size}</p>
                <div className="flex items-center space-x-4 mt-2">
                  <span>Qty: {item.quantity}</span>
                  <button
                    onClick={() => remove(item.productId, item.size)}
                    className="text-sm text-red-600 hover:underline"
                  >
                    Remove
                  </button>
                </div>
              </div>
              <div className="text-right">
                <p data-ghost-id={`cart.item.${item.productId}.price`} className="font-bold text-lg">
                  ${(item.price * item.quantity).toFixed(2)}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Order Summary */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 h-fit">
          <h2 className="text-xl font-bold mb-6">Order Summary</h2>

          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Subtotal</span>
              <span data-ghost-id="cart.subtotal" className="font-medium">
                ${subtotal.toFixed(2)}
              </span>
            </div>
            {discount > 0 && (
              <div className="flex justify-between text-green-600">
                <span>Discount</span>
                <span data-ghost-id="cart.discount" className="font-medium">
                  -${discount.toFixed(2)}
                </span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-gray-600">Shipping</span>
              <span data-ghost-id="cart.shipping">
                {shipping === 0 ? (
                  <span className="text-green-600">Free</span>
                ) : (
                  `$${shipping.toFixed(2)}`
                )}
              </span>
            </div>
            {shipping > 0 && (
              <p className="text-xs text-gray-500">
                Free shipping on orders over $75
              </p>
            )}
            <div className="flex justify-between">
              <span className="text-gray-600">Tax</span>
              <span data-ghost-id="cart.tax">${tax.toFixed(2)}</span>
            </div>
            <div className="border-t pt-3 flex justify-between text-lg font-bold">
              <span>Total</span>
              <span data-ghost-id="cart.total">${total.toFixed(2)}</span>
            </div>

            {/* Promo Code Input */}
            <div className="pt-4 border-t">
              <label className="block text-xs font-medium text-gray-700 mb-1">Promo Code</label>
              <div className="flex space-x-2">
                <input
                  type="text"
                  data-ghost-id="cart.promo_code"
                  value={promoCode}
                  onChange={(e) => setPromoCode(e.target.value)}
                  placeholder="Promo code"
                  className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <button
                  type="button"
                  data-ghost-id="cart.apply_promo"
                  onClick={handleApplyPromo}
                  className="bg-gray-800 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-700 transition-colors"
                >
                  Apply
                </button>
              </div>
              {promoError && (
                <p className="text-xs text-red-600 mt-1">{promoError}</p>
              )}
            </div>
          </div>

          <button
            data-ghost-id="cart.checkout_btn"
            onClick={() => navigate('/checkout')}
            className="w-full mt-6 bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors"
          >
            Proceed to Checkout
          </button>

          <div className="mt-4 flex items-center justify-center space-x-2 text-gray-500">
            <span className="text-sm">🔒 Secure checkout</span>
          </div>
        </div>
      </div>
    </div>
  );
}