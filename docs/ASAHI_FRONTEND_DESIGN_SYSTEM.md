# ASAHI Frontend Design System

Complete React component library and design specifications for ASAHI interface.

---

## Quick Start

```bash
# Create Next.js project
npx create-next-app@latest asahi-frontend --typescript

# Install dependencies
npm install tailwindcss recharts heroicons next

# Copy components below
# Set up Tailwind config
# Start dev server
npm run dev
```

---

## Color System

### Primary Colors
```
Orange Primary:    #FF6B35 (CTAs, highlights, primary actions)
Orange Light:      #FFB84D (hover states)
Orange Very Light: #FFF3E0 (subtle backgrounds)
```

### Neutral Colors
```
Dark Text:    #1A1A1A
Dark Gray:    #4A4A4A
Light Gray:   #F5F5F5
Border:       #E0E0E0
White:        #FFFFFF
```

### Semantic Colors
```
Success: #4CAF50
Error:   #F44336
Warning: #FF9800
Info:    #2196F3
```

---

## React Components

### 1. Button Component

```jsx
// components/Button.jsx

export function Button({ 
  children, 
  variant = 'primary', 
  size = 'md',
  ...props 
}) {
  const baseStyles = 'font-medium rounded transition duration-200';
  
  const variants = {
    primary: 'bg-[#FF6B35] text-white hover:bg-[#E55A24]',
    secondary: 'bg-[#F5F5F5] text-[#1A1A1A] hover:bg-[#E0E0E0]',
    outline: 'border-2 border-[#FF6B35] text-[#FF6B35] hover:bg-[#FFF3E0]',
    ghost: 'text-[#FF6B35] hover:bg-[#FFF3E0]',
  };
  
  const sizes = {
    sm: 'px-4 py-2 text-sm',
    md: 'px-6 py-3 text-base',
    lg: 'px-8 py-4 text-lg',
  };
  
  return (
    <button 
      className={`${baseStyles} ${variants[variant]} ${sizes[size]}`}
      {...props}
    >
      {children}
    </button>
  );
}
```

### 2. Navigation Bar

```jsx
// components/Navbar.jsx

export function Navbar() {
  return (
    <nav className="fixed top-0 w-full bg-white border-b border-[#E0E0E0] z-50">
      <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
        
        {/* Logo */}
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-[#FF6B35] flex items-center justify-center">
            <span className="text-white font-bold">A</span>
          </div>
          <span className="font-bold text-xl text-[#1A1A1A]">ASAHI</span>
        </div>
        
        {/* Menu */}
        <div className="hidden md:flex gap-8">
          <a href="#" className="text-[#4A4A4A] hover:text-[#FF6B35]">Products</a>
          <a href="#" className="text-[#4A4A4A] hover:text-[#FF6B35]">Docs</a>
          <a href="#" className="text-[#4A4A4A] hover:text-[#FF6B35]">Resources</a>
        </div>
        
        {/* Actions */}
        <div className="flex gap-4">
          <Button variant="ghost">Login</Button>
          <Button variant="primary">Sign Up</Button>
        </div>
      </div>
    </nav>
  );
}
```

### 3. Card Component

```jsx
// components/Card.jsx

export function Card({ children, highlight = false }) {
  return (
    <div className={`p-6 rounded-lg border transition ${
      highlight 
        ? 'border-[#FF6B35] bg-[#FFF3E0]' 
        : 'border-[#E0E0E0] bg-white hover:border-[#FF6B35]'
    }`}>
      {children}
    </div>
  );
}

// Feature Card
export function FeatureCard({ icon, title, description, highlight }) {
  return (
    <Card highlight={highlight}>
      <div className={`w-12 h-12 rounded-lg flex items-center justify-center mb-4 ${
        highlight ? 'bg-[#FF6B35] text-white' : 'bg-[#F5F5F5] text-[#FF6B35]'
      }`}>
        {icon}
      </div>
      <h3 className="text-lg font-bold text-[#1A1A1A] mb-2">{title}</h3>
      <p className="text-[#4A4A4A] text-sm leading-relaxed">{description}</p>
    </Card>
  );
}
```

### 4. Metric Card

```jsx
// components/MetricCard.jsx

export function MetricCard({ value, label, unit = "" }) {
  return (
    <Card>
      <div className="text-center">
        <div className="text-5xl font-bold text-[#FF6B35] mb-2">
          {value}{unit}
        </div>
        <div className="text-[#4A4A4A] text-sm font-medium">
          {label}
        </div>
      </div>
    </Card>
  );
}
```

### 5. Input Component

```jsx
// components/Input.jsx

export function Input({ label, placeholder, type = 'text', ...props }) {
  return (
    <div className="mb-6">
      {label && (
        <label className="block text-sm font-medium text-[#1A1A1A] mb-2">
          {label}
        </label>
      )}
      <input
        type={type}
        placeholder={placeholder}
        className="w-full px-4 py-3 border border-[#E0E0E0] rounded-lg focus:border-[#FF6B35] focus:ring-2 focus:ring-[#FFF3E0] outline-none transition"
        {...props}
      />
    </div>
  );
}
```

### 6. Toggle/Switch

```jsx
// components/Toggle.jsx

export function Toggle({ enabled, onChange }) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-8 w-16 items-center rounded-full transition ${
        enabled ? 'bg-[#FF6B35]' : 'bg-[#E0E0E0]'
      }`}
    >
      <span
        className={`inline-block h-6 w-6 transform rounded-full bg-white transition ${
          enabled ? 'translate-x-9' : 'translate-x-1'
        }`}
      />
    </button>
  );
}
```

### 7. Sidebar

```jsx
// components/Sidebar.jsx

export function Sidebar({ currentPage }) {
  const navItems = [
    { icon: '📊', label: 'Dashboard', path: '/dashboard' },
    { icon: '⚡', label: 'Inference', path: '/inference' },
    { icon: '💾', label: 'Cache', path: '/cache' },
    { icon: '📈', label: 'Analytics', path: '/analytics' },
    { icon: '⚙️', label: 'Settings', path: '/settings' },
  ];

  return (
    <aside className="w-64 bg-white border-r border-[#E0E0E0] h-screen sticky top-0">
      <div className="p-6 border-b border-[#E0E0E0]">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-[#FF6B35]" />
          <span className="font-bold">ASAHI</span>
        </div>
      </div>
      
      <nav className="p-6">
        {navItems.map(item => (
          <a
            key={item.path}
            href={item.path}
            className={`flex items-center gap-3 px-4 py-3 rounded-lg mb-2 transition ${
              currentPage === item.path
                ? 'bg-[#FFF3E0] text-[#FF6B35]'
                : 'text-[#4A4A4A] hover:bg-[#FFF3E0] hover:text-[#FF6B35]'
            }`}
          >
            <span>{item.icon}</span>
            <span className="font-medium">{item.label}</span>
          </a>
        ))}
      </nav>
    </aside>
  );
}
```

### 8. Hero Section

```jsx
// components/HeroSection.jsx

export function HeroSection() {
  return (
    <section className="pt-32 pb-20 bg-white">
      <div className="max-w-7xl mx-auto px-6 grid grid-cols-2 gap-16 items-center">
        
        <div>
          <div className="text-sm font-medium text-[#FF6B35] mb-4">
            BUILD INTELLIGENT INFERENCE
          </div>
          
          <h1 className="text-5xl font-bold text-[#1A1A1A] mb-6 leading-tight">
            The inference optimizer for <span className="text-[#FF6B35]">cost efficiency</span>
          </h1>
          
          <p className="text-lg text-[#4A4A4A] mb-8">
            ASAHI intelligently routes requests, caches semantically similar queries, 
            and decomposes workflows to cut inference costs by 85-97%.
          </p>
          
          <div className="flex gap-4">
            <Button variant="primary">Start Building</Button>
            <Button variant="outline">Get Demo</Button>
          </div>
        </div>
        
        <div className="bg-[#FFF3E0] rounded-lg p-12 h-96 flex items-center justify-center">
          <div className="text-center text-[#4A4A4A]">
            [Architecture Diagram Placeholder]
          </div>
        </div>
      </div>
    </section>
  );
}
```

### 9. Dashboard Layout

```jsx
// components/Dashboard.jsx

export function Dashboard({ children }) {
  const [currentPage, setCurrentPage] = React.useState('/dashboard');
  
  return (
    <div className="flex h-screen bg-[#F5F5F5]">
      <Sidebar currentPage={currentPage} />
      
      <main className="flex-1 overflow-auto">
        <header className="bg-white border-b border-[#E0E0E0] px-8 py-6">
          <h1 className="text-2xl font-bold text-[#1A1A1A]">Dashboard</h1>
          <p className="text-[#4A4A4A] mt-1">Monitor your ASAHI optimization</p>
        </header>
        
        <div className="p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
```

---

## Page Examples

### Landing Page

```jsx
// pages/index.jsx

export default function Home() {
  return (
    <div className="bg-white">
      <Navbar />
      <HeroSection />
      
      <section className="py-20 bg-[#F5F5F5]">
        <div className="max-w-7xl mx-auto px-6">
          <h2 className="text-4xl font-bold text-center mb-16">Why ASAHI?</h2>
          
          <div className="grid grid-cols-3 gap-8">
            <FeatureCard
              title="Tier 1: Exact Match"
              description="Zero cost exact-match caching"
            />
            <FeatureCard
              title="Tier 2: Semantic"
              description="85%+ similarity detection"
              highlight={true}
            />
            <FeatureCard
              title="Tier 3: Intermediate"
              description="Workflow step reuse"
            />
          </div>
        </div>
      </section>
      
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-6">
          <h2 className="text-4xl font-bold text-center mb-16">Results</h2>
          
          <div className="grid grid-cols-4 gap-6">
            <MetricCard value="87" label="Cost Savings" unit="%" />
            <MetricCard value="150" label="Latency" unit="ms" />
            <MetricCard value="98" label="Accuracy" unit="%" />
            <MetricCard value="4.8" label="Quality" unit="/5" />
          </div>
        </div>
      </section>
      
      <section className="py-20 bg-[#FF6B35]">
        <div className="max-w-4xl mx-auto px-6 text-center text-white">
          <h2 className="text-4xl font-bold mb-6">Ready to optimize?</h2>
          <Button variant="secondary">Start Building</Button>
        </div>
      </section>
    </div>
  );
}
```

### Dashboard Page

```jsx
// pages/dashboard.jsx

export default function DashboardPage() {
  return (
    <Dashboard>
      <div className="grid grid-cols-4 gap-6 mb-8">
        <MetricCard value="87" label="Cost Savings" unit="%" />
        <MetricCard value="1,024" label="Requests" unit="" />
        <MetricCard value="$12.45" label="Total Cost" unit="" />
        <MetricCard value="4.8" label="Quality" unit="/5" />
      </div>
      
      <div className="grid grid-cols-2 gap-6">
        <Card>
          <h3 className="text-lg font-bold mb-4">Cache Hit Rate</h3>
          <div className="h-64 bg-[#FFF3E0] rounded flex items-center justify-center">
            [Chart visualization]
          </div>
        </Card>
        
        <Card>
          <h3 className="text-lg font-bold mb-4">Cost by Model</h3>
          <div className="h-64 bg-[#FFF3E0] rounded flex items-center justify-center">
            [Chart visualization]
          </div>
        </Card>
      </div>
    </Dashboard>
  );
}
```

---

## Tailwind Configuration

```js
// tailwind.config.js

module.exports = {
  content: [
    './pages/**/*.{js,jsx}',
    './components/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        'asahi': {
          'orange': '#FF6B35',
          'orange-light': '#FFB84D',
          'orange-very-light': '#FFF3E0',
        },
      },
      fontFamily: {
        'inter': ['Inter', 'sans-serif'],
      },
    },
  },
};
```

---

## Project Structure

```
asahi-frontend/
├── pages/
│   ├── index.jsx           # Landing
│   ├── dashboard.jsx       # Dashboard
│   ├── inference.jsx       # Inference
│   ├── cache.jsx           # Cache
│   ├── analytics.jsx       # Analytics
│   ├── settings.jsx        # Settings
│   └── api/
│       └── infer.js        # API routes
├── components/
│   ├── Navbar.jsx
│   ├── Sidebar.jsx
│   ├── Button.jsx
│   ├── Card.jsx
│   ├── Input.jsx
│   ├── Toggle.jsx
│   ├── MetricCard.jsx
│   ├── FeatureCard.jsx
│   ├── HeroSection.jsx
│   └── Dashboard.jsx
├── styles/
│   └── globals.css
├── tailwind.config.js
├── next.config.js
└── package.json
```

---

## Installation & Setup

```bash
# 1. Create project
npx create-next-app@latest asahi-frontend --typescript

# 2. Install deps
cd asahi-frontend
npm install tailwindcss recharts heroicons

# 3. Copy components
# Copy all component files from above

# 4. Dev server
npm run dev

# 5. Build
npm run build
npm start
```

---

## API Integration

```jsx
// lib/api.js

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function infer(prompt, options = {}) {
  const response = await fetch(`${API_BASE}/infer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, ...options }),
  });
  return response.json();
}

export async function getMetrics() {
  return fetch(`${API_BASE}/metrics`).then(r => r.json());
}
```

---

Complete and ready to implement! 🎨
