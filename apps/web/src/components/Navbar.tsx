"use client";

import Link from "next/link";
import { Shield } from "lucide-react";
import { motion } from "framer-motion";

export default function Navbar() {
  return (
    <nav className="fixed top-0 left-0 w-full z-50 backdrop-blur-2xl" style={{ background: 'rgba(6,6,20,0.72)', borderBottom: '1px solid rgba(99,102,241,0.15)' }}>
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <Shield className="w-5 h-5 text-white group-hover:scale-110 transition-transform duration-300" />
          <span className="text-lg font-medium tracking-wide text-white">
            Merlin AI
          </span>
        </Link>

        {/* CTA Button */}
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="text-black px-6 py-2 text-sm font-medium tracking-wide transition-all"
          style={{ background: 'linear-gradient(135deg, #ffffff 0%, #e0e7ff 100%)' }}
        >
          Begin Analysis
        </motion.button>
      </div>
    </nav>
  );
}
