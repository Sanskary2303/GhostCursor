import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCart } from '../cart/CartContext';

export function Checkout() {
  const navigate = useNavigate();
  const cart = useCart();
  const [formData, setFormData] = useState({
    email: '',
    firstName: '',
    lastName: '',
    address: '',
    city: '',
    state: '',
    zip: '',
    phone: '',
    cardNumber: '',
    expiry: '',
    cvv: '',
  });
  const [savedAddress, setSavedAddress] = useState('123 Main St, New York, NY 10001');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    cart.clear();
    navigate('/orders');
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const subtotal = cart.subtotal;
  const shipping = subtotal > 75 || subtotal === 0 ? 0 : 8.99;
  const tax = subtotal * 0.08;
  const total = subtotal + shipping + tax;

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">Checkout</h1>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Form Section */}
        <div className="lg:col-span-2 space-y-8">
          {/* Contact */}
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-xl font-bold mb-4">Contact Information</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Email Address</label>
                <input
                  data-ghost-id="checkout.email"
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  required
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="your@email.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Phone Number</label>
                <input
                  data-ghost-id="checkout.phone"
                  type="tel"
                  name="phone"
                  value={formData.phone}
                  onChange={handleChange}
                  required
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="(555) 123-4567"
                />
              </div>
            </div>
          </section>

          {/* Shipping Address */}
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-xl font-bold mb-4">Shipping Address</h2>

            {/* Saved Address */}
            <div className="mb-6 p-4 bg-gray-50 rounded-lg">
              <label className="flex items-start space-x-3 cursor-pointer">
                <input
                  type="radio"
                  name="addressType"
                  value="saved"
                  defaultChecked
                  onChange={() => setFormData({ ...formData, address: savedAddress })}
                  className="mt-1"
                />
                <div>
                  <p className="font-medium">Use saved address:</p>
                  <p data-ghost-id="checkout.saved_address" className="text-gray-600 text-sm">
                    {savedAddress}
                  </p>
                </div>
              </label>
            </div>

            {/* New Address Form */}
            <div className="space-y-4">
              <label className="flex items-start space-x-3 cursor-pointer mb-4">
                <input
                  type="radio"
                  name="addressType"
                  value="new"
                  className="mt-1"
                />
                <span className="font-medium">Enter a new address</span>
              </label>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">First Name</label>
                  <input
                    data-ghost-id="checkout.first_name"
                    type="text"
                    name="firstName"
                    value={formData.firstName}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Last Name</label>
                  <input
                    data-ghost-id="checkout.last_name"
                    type="text"
                    name="lastName"
                    value={formData.lastName}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Street Address</label>
                <input
                  data-ghost-id="checkout.address"
                  type="text"
                  name="address"
                  value={formData.address}
                  onChange={handleChange}
                  required
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">City</label>
                  <input
                    data-ghost-id="checkout.city"
                    type="text"
                    name="city"
                    value={formData.city}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">State</label>
                  <select
                    data-ghost-id="checkout.state"
                    name="state"
                    value={formData.state}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select</option>
                    <option value="NY">New York</option>
                    <option value="CA">California</option>
                    <option value="TX">Texas</option>
                    <option value="FL">Florida</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">ZIP Code</label>
                  <input
                    data-ghost-id="checkout.zip"
                    data-ghost-observe
                    type="text"
                    name="zip"
                    value={formData.zip}
                    onChange={handleChange}
                    required
                    pattern="\d{5}"
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    placeholder="10001"
                  />
                </div>
              </div>
            </div>
          </section>

          {/* Payment */}
          <section className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-xl font-bold mb-4">Payment Information</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Card Number</label>
                <input
                  type="text"
                  name="cardNumber"
                  autoComplete="cc-number"
                  value={formData.cardNumber}
                  onChange={handleChange}
                  required
                  pattern="\d{16}"
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="1234 5678 9012 3456"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Expiry Date</label>
                  <input
                    type="text"
                    name="expiry"
                    autoComplete="cc-exp"
                    value={formData.expiry}
                    onChange={handleChange}
                    required
                    pattern="\d{2}/\d{2}"
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    placeholder="MM/YY"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">CVV</label>
                  <input
                    type="text"
                    name="cvv"
                    autoComplete="cc-csc"
                    value={formData.cvv}
                    onChange={handleChange}
                    required
                    pattern="\d{3,4}"
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    placeholder="123"
                  />
                </div>
              </div>
            </div>
          </section>
        </div>

        {/* Order Summary */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 h-fit">
          <h2 className="text-xl font-bold mb-4">Order Summary</h2>
          <div className="space-y-3 text-sm border-b pb-4">
            {cart.items.length === 0 ? (
              <p className="text-gray-500">Your cart is empty.</p>
            ) : (
              cart.items.map((item) => (
                <div key={`${item.productId}-${item.size}`} className="flex justify-between">
                  <span>
                    {item.name} (Size {item.size}) × {item.quantity}
                  </span>
                  <span>${(item.price * item.quantity).toFixed(2)}</span>
                </div>
              ))
            )}
            <div className="flex justify-between text-gray-600">
              <span>Shipping</span>
              <span className={shipping === 0 ? "text-green-600" : ""}>
                {shipping === 0 ? "Free" : `$${shipping.toFixed(2)}`}
              </span>
            </div>
            <div className="flex justify-between text-gray-600">
              <span>Tax</span>
              <span>${tax.toFixed(2)}</span>
            </div>
          </div>
          <div className="flex justify-between pt-4 text-lg font-bold">
            <span>Total</span>
            <span data-ghost-id="checkout.total">${total.toFixed(2)}</span>
          </div>

          <button
            type="submit"
            data-ghost-id="checkout.place_order"
            className="w-full mt-6 bg-blue-600 text-white py-4 rounded-lg font-semibold hover:bg-blue-700 transition-colors"
          >
            Place Order
          </button>
        </div>
      </form>
    </div>
  );
}