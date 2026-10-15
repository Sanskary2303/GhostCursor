import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

const PRODUCTS_DATA: Record<string, any> = {
  'air-max-90': {
    id: 'air-max-90',
    name: 'Nike Air Max 90',
    price: 129.99,
    description: "The Nike Air Max 90 stays true to its OG running roots with the iconic Waffle sole, stitched overlays and classic TPU accents. Fresh colors give a modern look while Max Air cushioning provides lasting comfort.",
    sizes: [
      { size: '7', available: 12 },
      { size: '8', available: 18 },
      { size: '9', available: 15 },
      { size: '10', available: 20 },
      { size: '11', available: 8 },
      { size: '12', available: 5 },
      { size: '13', available: 3 },
    ],
    colors: ['Black', 'White', 'Red'],
    details: [
      ' Leather and textile upper for durability',
      ' Max Air cushioning provides comfort',
      'rubber Waffle outsole for traction',
      ' Padded collar and tongue',
    ],
  },
  'jordan-1': {
    id: 'jordan-1',
    name: 'Air Jordan 1 Retro',
    price: 179.99,
    description: "The Air Jordan 1 Retro brings back the iconic design that started it all.",
    sizes: [
      { size: '8', available: 10 },
      { size: '9', available: 14 },
      { size: '10', available: 16 },
      { size: '11', available: 9 },
      { size: '12', available: 4 },
    ],
    colors: ['Black/Red', 'White/Blue'],
    details: ['Premium leather upper', 'Nike Air cushioning', 'Rubber outsole'],
  },
};

export function ProductDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [selectedSize, setSelectedSize] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState<string>('');
  const [quantity, setQuantity] = useState(1);
  const [cartCount, setCartCount] = useState(0);

  const product = PRODUCTS_DATA[id || ''] || PRODUCTS_DATA['air-max-90'];

  const handleAddToCart = () => {
    if (!selectedSize) {
      alert('Please select a size');
      return;
    }
    setCartCount(cartCount + quantity);
    alert(`Added ${product.name} (Size ${selectedSize}) to cart!`);
  };

  return (
    <div className="max-w-6xl mx-auto">
      {/* Breadcrumb */}
      <nav className="flex items-center space-x-2 text-sm text-gray-500 mb-6">
        <button onClick={() => navigate('/')} className="hover:text-blue-600">Home</button>
        <span>/</span>
        <span className="text-gray-900">{product.name}</span>
      </nav>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
        {/* Product Image */}
        <div className="bg-gray-100 rounded-2xl aspect-square flex items-center justify-center text-9xl">
          {product.id === 'air-max-90' ? '🟦' : product.id === 'jordan-1' ? '🟥' : '👟'}
        </div>

        {/* Product Info */}
        <div className="space-y-6">
          <div>
            <h1 data-ghost-id="product.title" className="text-3xl font-bold mb-2">
              {product.name}
            </h1>
            <p data-ghost-id="product.price" className="text-3xl font-bold text-blue-600">
              ${product.price}
            </p>
          </div>

          <p className="text-gray-600 leading-relaxed">{product.description}</p>

          {/* Color Selection */}
          <div>
            <label className="block text-sm font-medium mb-3">Color</label>
            <div className="flex items-center space-x-3">
              {product.colors.map((color: string) => (
                <button
                  key={color}
                  data-ghost-id={`product.color.${color.toLowerCase().replace('/', '-')}`}
                  onClick={() => setSelectedColor(color)}
                  className={`px-4 py-2 border rounded-lg text-sm transition-colors ${
                    selectedColor === color
                      ? 'border-blue-600 bg-blue-50 text-blue-600'
                      : 'border-gray-300 hover:border-gray-400'
                  }`}
                >
                  {color}
                </button>
              ))}
            </div>
          </div>

          {/* Size Selection */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="block text-sm font-medium">Select Size (US Men's)</label>
              <button className="text-sm text-blue-600 hover:underline">Size Guide</button>
            </div>
            <div className="grid grid-cols-4 gap-2">
              {product.sizes.map((sizeInfo: any) => (
                <button
                  key={sizeInfo.size}
                  data-ghost-id={`product.size.${sizeInfo.size}`}
                  onClick={() => setSelectedSize(sizeInfo.size)}
                  disabled={sizeInfo.available === 0}
                  className={`py-3 border rounded-lg text-sm font-medium transition-colors ${
                    selectedSize === sizeInfo.size
                      ? 'border-blue-600 bg-blue-600 text-white'
                      : sizeInfo.available === 0
                      ? 'border-gray-200 text-gray-300 cursor-not-allowed'
                      : 'border-gray-300 hover:border-gray-400'
                  }`}
                >
                  {sizeInfo.size}
                  {sizeInfo.available < 5 && sizeInfo.available > 0 && (
                    <span className="block text-xs opacity-70">Only {sizeInfo.available} left</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Quantity */}
          <div>
            <label className="block text-sm font-medium mb-3">Quantity</label>
            <div className="flex items-center space-x-3">
              <button
                data-ghost-id="product.quantity.decrease"
                onClick={() => setQuantity(Math.max(1, quantity - 1))}
                className="w-10 h-10 border rounded-lg flex items-center justify-center hover:bg-gray-50"
              >
                -
              </button>
              <span className="w-12 text-center font-medium">{quantity}</span>
              <button
                data-ghost-id="product.quantity.increase"
                onClick={() => setQuantity(quantity + 1)}
                className="w-10 h-10 border rounded-lg flex items-center justify-center hover:bg-gray-50"
              >
                +
              </button>
            </div>
          </div>

          {/* Add to Cart */}
          <div className="flex items-center space-x-4 pt-4">
            <button
              data-ghost-id="product.add_to_cart_btn"
              onClick={handleAddToCart}
              className="flex-1 bg-blue-600 text-white py-4 rounded-xl font-semibold hover:bg-blue-700 transition-colors"
            >
              Add to Cart
            </button>
            <button
              data-ghost-id="product.wishlist"
              className="w-14 h-14 border border-gray-300 rounded-xl flex items-center justify-center hover:bg-gray-50"
            >
              ❤️
            </button>
          </div>

          {/* Cart notification */}
          {cartCount > 0 && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-green-800">
              ✅ {cartCount} item(s) in your cart!{' '}
              <button
                onClick={() => navigate('/cart')}
                className="underline font-medium hover:text-green-900"
              >
                View Cart
              </button>
            </div>
          )}

          {/* Product Details */}
          <div className="border-t pt-6">
            <h3 className="font-semibold mb-4">Product Details</h3>
            <ul className="space-y-2">
              {product.details.map((detail: string, idx: number) => (
                <li key={idx} className="flex items-start space-x-2 text-sm text-gray-600">
                  <span className="text-blue-600">•</span>
                  <span>{detail}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}