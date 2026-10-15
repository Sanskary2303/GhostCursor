import React from 'react';
import { Link } from 'react-router-dom';

const PRODUCTS = [
  {
    id: 'air-max-90',
    name: 'Nike Air Max 90',
    price: 129.99,
    image: '🟦', // Placeholder
    sizes: ['7', '8', '9', '10', '11', '12', '13'],
    colors: ['Black', 'White', 'Red'],
  },
  {
    id: 'jordan-1',
    name: 'Air Jordan 1 Retro',
    price: 179.99,
    image: '🟥',
    sizes: ['8', '9', '10', '11', '12'],
    colors: ['Black/Red', 'White/Blue'],
  },
  {
    id: 'yeezy-350',
    name: 'Yeezy Boost 350',
    price: 229.99,
    image: '🟨',
    sizes: ['7', '8', '9', '10', '11'],
    colors: ['Beige', 'Black'],
  },
  {
    id: 'ultraboost',
    name: 'Adidas Ultraboost 22',
    price: 189.99,
    image: '⚫',
    sizes: ['8', '9', '10', '11', '12'],
    colors: ['Black', 'White', 'Blue'],
  },
];

export function Home() {
  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <section className="bg-gradient-to-r from-blue-600 to-blue-800 rounded-2xl p-12 text-white">
        <h1 className="text-4xl font-bold mb-4">Welcome to ShopHive</h1>
        <p className="text-xl mb-6 opacity-90">
          Premium sneakers and sportswear. Free shipping on orders over $75.
        </p>
        <button
          data-ghost-id="hero.shop_now"
          className="bg-white text-blue-600 px-8 py-3 rounded-lg font-semibold hover:bg-gray-100 transition-colors"
        >
          Shop Now
        </button>
      </section>

      {/* Product Grid */}
      <section>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold">Featured Products</h2>
          <div className="flex items-center space-x-4">
            <label className="text-sm text-gray-600">Sort by:</label>
            <select
              data-ghost-id="products.sort"
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            >
              <option>Featured</option>
              <option>Price: Low to High</option>
              <option>Price: High to Low</option>
              <option>Newest</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {PRODUCTS.map((product) => (
            <Link
              key={product.id}
              to={`/product/${product.id}`}
              data-ghost-id={`product.card.${product.id}`}
              className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-lg transition-shadow group"
            >
              {/* Product Image Placeholder */}
              <div className="aspect-square bg-gray-100 flex items-center justify-center text-6xl">
                {product.image}
              </div>

              {/* Product Info */}
              <div className="p-4">
                <h3
                  data-ghost-id={`product.${product.id}.title`}
                  className="font-semibold text-gray-900 mb-2 group-hover:text-blue-600 transition-colors"
                >
                  {product.name}
                </h3>
                <div className="flex items-center justify-between">
                  <p
                    data-ghost-id={`product.${product.id}.price`}
                    className="text-xl font-bold text-blue-600"
                  >
                    ${product.price}
                  </p>
                  <span className="text-sm text-gray-500">
                    {product.sizes.length} sizes
                  </span>
                </div>
                <div className="mt-2 flex items-center space-x-1">
                  {product.colors.map((color, idx) => (
                    <span
                      key={idx}
                      className="w-4 h-4 rounded-full border border-gray-300"
                      style={{
                        backgroundColor:
                          color === 'Black'
                            ? '#000'
                            : color === 'White'
                            ? '#fff'
                            : color === 'Red'
                            ? '#ef4444'
                            : color === 'Blue'
                            ? '#3b82f6'
                            : color === 'Beige'
                            ? '#d4a574'
                            : '#6b7280',
                      }}
                    />
                  ))}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* Info Section */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12">
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <div className="text-3xl mb-3">🚚</div>
          <h3 className="font-semibold mb-2">Free Shipping</h3>
          <p className="text-sm text-gray-600">
            Free shipping on all orders over $75
          </p>
        </div>
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <div className="text-3xl mb-3">↩️</div>
          <h3 className="font-semibold mb-2">30-Day Returns</h3>
          <p className="text-sm text-gray-600">
            Easy returns within 30 days of purchase
          </p>
        </div>
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <div className="text-3xl mb-3">💳</div>
          <h3 className="font-semibold mb-2">Secure Checkout</h3>
          <p className="text-sm text-gray-600">
            Your payment information is always safe
          </p>
        </div>
      </section>
    </div>
  );
}