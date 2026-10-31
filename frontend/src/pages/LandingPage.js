import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import {
  Truck, Shield, FileText, MapPin, CreditCard,
  CheckCircle, ArrowRight, Clock, Thermometer,
  ShieldCheck, Route, HeartHandshake, CloudSnow, Pill, Search, Store
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const LandingPage = () => {
  const navigate = useNavigate();
  const [network, setNetwork] = useState(null);
  const [sealCode, setSealCode] = useState('');

  useEffect(() => {
    axios.get(`${API}/public/network`).then((r) => setNetwork(r.data)).catch(() => {});
  }, []);

  const permits = [
    { name: 'CVOR Certified', desc: 'Commercial Vehicle Operator\'s Registration' },
    { name: 'TDG Training', desc: 'Transportation of Dangerous Goods Certificate' },
    { name: 'Vulnerable Sector Check', desc: 'Background check for medical transport' },
    { name: 'Commercial Insurance', desc: 'Minimum $2M liability coverage' }
  ];

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-lg border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                <Truck className="w-6 h-6 text-white" />
              </div>
              <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
              <Badge variant="outline" className="ml-2 text-blue-700 border-blue-200 bg-blue-50">Ontario</Badge>
            </div>
            <div className="hidden md:flex items-center gap-6">
              <a href="#signature" className="nav-link">Why MediTrans</a>
              <a href="#features" className="nav-link">Features</a>
              <a href="#pricing" className="nav-link">Pricing</a>
              <a href="#permits" className="nav-link">Requirements</a>
              <Button 
                variant="outline" 
                onClick={() => navigate('/login')}
                data-testid="nav-login-btn"
              >
                Log In
              </Button>
              <Button 
                onClick={() => navigate('/register')}
                className="bg-blue-600 hover:bg-blue-700 rounded-full"
                data-testid="nav-register-btn"
              >
                Start Driving
              </Button>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-6 hero-gradient">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="text-white animate-fade-in-up">
              <Badge className="bg-emerald-500/20 text-emerald-200 border-emerald-400/30 mb-6">
                <Pill className="w-3.5 h-3.5 mr-1.5" /> Canada's First Pharmacy-Only Delivery Network
              </Badge>
              <h1 className="font-archivo font-black text-4xl sm:text-5xl lg:text-6xl leading-tight mb-6">
                Prescriptions Delivered. Sealed. Verified.
              </h1>
              <p className="text-lg text-slate-300 mb-8 max-w-xl">
                MediTrans serves only pharmacies and licensed health shops — no food, no parcels, no distractions.
                Every prescription travels under a tamper-evident seal your patients can verify online.
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <Button 
                  size="lg"
                  onClick={() => navigate('/register')}
                  className="bg-blue-600 hover:bg-blue-700 rounded-full text-lg px-8"
                  data-testid="hero-start-driving-btn"
                >
                  Start Driving <ArrowRight className="ml-2 w-5 h-5" />
                </Button>
                <Button 
                  size="lg"
                  variant="outline"
                  onClick={() => navigate('/facility')}
                  className="border-slate-400 text-white hover:bg-white/10 rounded-full text-lg px-8"
                  data-testid="hero-book-transport-btn"
                >
                  Book Transport
                </Button>
              </div>
            </div>
            <div className="relative animate-fade-in-up stagger-2">
              <img 
                src="https://images.pexels.com/photos/6818157/pexels-photo-6818157.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940" 
                alt="Medical courier handling a secure clinical parcel"
                className="rounded-2xl shadow-2xl w-full"
              />
              {/* Floating card */}
              <Card className="glass-card absolute -bottom-6 -left-6 p-4 animate-pulse-glow">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
                    <Truck className="w-5 h-5 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-900">Live Job</p>
                    <p className="text-xs text-slate-500">Insulin Delivery - 12km</p>
                  </div>
                  <Badge className="bg-green-100 text-green-700 ml-2">$45</Badge>
                </div>
              </Card>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-20 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <Badge className="mb-4">How It Works</Badge>
            <h2 className="font-archivo font-bold text-3xl md:text-4xl text-slate-900 mb-4">
              Medical Transport Made Simple
            </h2>
            <p className="text-slate-600 max-w-2xl mx-auto">
              Our platform connects certified drivers with healthcare facilities, 
              labs, and pharmacies across Ontario.
            </p>
          </div>
          
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { icon: Shield, title: 'Verified Drivers', desc: 'All drivers are certified with CVOR, TDG, and background checks' },
              { icon: Clock, title: 'Real-Time Matching', desc: 'Get matched with urgent deliveries in your area instantly' },
              { icon: Thermometer, title: 'Temperature Controlled', desc: 'Specialized transport for temperature-sensitive biologicals' }
            ].map((feature, i) => (
              <Card key={i} className="card-hover p-8 border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
                <div className="w-14 h-14 bg-blue-100 rounded-xl flex items-center justify-center mb-6">
                  <feature.icon className="w-7 h-7 text-blue-600" />
                </div>
                <h3 className="font-archivo font-bold text-xl text-slate-900 mb-3">{feature.title}</h3>
                <p className="text-slate-600">{feature.desc}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Ontario Compliance Section */}
      <section id="permits" className="py-20 px-6 bg-slate-100">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <Badge className="bg-red-100 text-red-700 border-red-200 mb-4">Ontario Compliance</Badge>
              <h2 className="font-archivo font-bold text-3xl md:text-4xl text-slate-900 mb-4">
                Meet All Provincial Requirements
              </h2>
              <p className="text-slate-600 mb-8">
                We help you understand and obtain all necessary permits and licenses required 
                by the Ontario Ministry of Transportation and Transport Canada.
              </p>
              <div className="space-y-4">
                {permits.map((permit, i) => (
                  <div key={i} className="flex items-start gap-4 p-4 bg-white rounded-lg shadow-sm">
                    <CheckCircle className="w-6 h-6 text-emerald-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <h4 className="font-semibold text-slate-900">{permit.name}</h4>
                      <p className="text-sm text-slate-500">{permit.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
              <Button 
                onClick={() => navigate('/permits')}
                className="mt-8 bg-slate-900 hover:bg-slate-800 rounded-full"
                data-testid="view-requirements-btn"
              >
                View All Requirements <ArrowRight className="ml-2 w-4 h-4" />
              </Button>
            </div>
            <div>
              <img 
                src="https://images.pexels.com/photos/16669433/pexels-photo-16669433.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"
                alt="Toronto skyline representing Ontario-wide coverage"
                className="rounded-2xl shadow-xl"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Signature Suite — what no other app does */}
      <section id="signature" className="py-20 px-6 bg-slate-900">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-14">
            <Badge className="bg-emerald-500/15 text-emerald-300 border-emerald-500/30 mb-4">Only on MediTrans</Badge>
            <h2 className="font-archivo font-bold text-3xl md:text-4xl text-white mb-4">
              Built for prescriptions. Nothing else.
            </h2>
            <p className="text-slate-400 max-w-2xl mx-auto">
              General couriers carry everything. We carry only what pharmacies and health shops dispense —
              and built four signature protections no other platform offers.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { icon: ShieldCheck, title: 'SealTrace™ Custody', accent: 'text-emerald-400 bg-emerald-500/10',
                desc: 'Every delivery gets a tamper-evident seal code. Checked at pickup, checked at handoff, verifiable by anyone — patient, pharmacist or auditor.' },
              { icon: Route, title: 'Neighbourhood Routes', accent: 'text-blue-400 bg-blue-500/10',
                desc: 'Deliveries heading to the same community bundle into one route — drivers earn a +10% route bonus, pharmacies get faster coverage.' },
              { icon: HeartHandshake, title: 'Care Handoff', accent: 'text-pink-400 bg-pink-500/10',
                desc: 'For seniors and veterans: the courier waits, confirms the patient in person, and never leaves medication at the door. Ever.' },
              { icon: CloudSnow, title: 'Storm-Ready Promise', accent: 'text-cyan-400 bg-cyan-500/10',
                desc: 'Winter-equipped drivers opt in to storm duty, so critical medication still moves when Ontario weather shuts everything else down.' }
            ].map((f, i) => (
              <Card key={i} className="bg-slate-800/60 border border-slate-700/60 p-6 card-hover" data-testid={`signature-card-${i}`}>
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-5 ${f.accent}`}>
                  <f.icon className="w-6 h-6" />
                </div>
                <h3 className="font-archivo font-bold text-lg text-white mb-2">{f.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{f.desc}</p>
              </Card>
            ))}
          </div>

          {/* Verify a delivery inline */}
          <div className="mt-12 max-w-xl mx-auto text-center">
            <p className="text-slate-300 text-sm mb-3 font-medium">Received a MediTrans delivery? Verify its seal:</p>
            <form
              className="flex gap-2"
              onSubmit={(e) => { e.preventDefault(); if (sealCode.trim()) navigate(`/verify/${encodeURIComponent(sealCode.trim().toUpperCase())}`); }}
            >
              <Input
                value={sealCode}
                onChange={(e) => setSealCode(e.target.value)}
                placeholder="Seal code, e.g. MT-4F7A2C"
                className="h-12 bg-slate-800 border-slate-700 text-white placeholder:text-slate-500 font-mono uppercase"
                data-testid="landing-seal-input"
              />
              <Button type="submit" className="h-12 px-6 rounded-full bg-emerald-600 hover:bg-emerald-700" data-testid="landing-verify-btn">
                <Search className="w-4 h-4 mr-1" /> Verify
              </Button>
            </form>
          </div>
        </div>
      </section>

      {/* Trusted Pharmacy Network */}
      <section id="network" className="py-20 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-12">
            <Badge className="bg-blue-100 text-blue-700 border-blue-200 mb-4">Trusted Pharmacy Network</Badge>
            <h2 className="font-archivo font-bold text-3xl md:text-4xl text-slate-900 mb-4">
              A growing network — built on verified deliveries
            </h2>
            <p className="text-slate-600 max-w-2xl mx-auto">
              Every number below is live from our sealed custody records. As more pharmacies trust MediTrans,
              the network gets stronger for everyone.
            </p>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 max-w-4xl mx-auto mb-12" data-testid="network-stats">
            {[
              [network ? network.facilities_total : '—', 'Partner facilities'],
              [network ? network.deliveries_completed : '—', 'Deliveries completed'],
              [network ? network.drivers_approved : '—', 'Verified couriers'],
              [network ? network.seal_checks_passed : '—', 'Seal checks passed']
            ].map(([num, label], i) => (
              <div key={i} className="text-center">
                <p className="font-archivo font-black text-4xl md:text-5xl text-blue-600">{num}</p>
                <p className="text-sm text-slate-500 mt-1">{label}</p>
              </div>
            ))}
          </div>

          {network && network.network.length > 0 && (
            <div className="flex flex-wrap justify-center gap-3 max-w-4xl mx-auto" data-testid="network-partners">
              {network.network.map((f, i) => (
                <div key={i} className="inline-flex items-center gap-2 px-4 py-2 bg-slate-50 border border-slate-200 rounded-full">
                  <Store className="w-4 h-4 text-blue-600" />
                  <span className="text-sm font-medium text-slate-800">{f.name}</span>
                  <span className="text-xs text-slate-400">{f.city}</span>
                  {f.deliveries > 0 && <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">{f.deliveries} delivered</Badge>}
                </div>
              ))}
            </div>
          )}

          <div className="text-center mt-10">
            <p className="text-slate-500 text-sm mb-4">Run a pharmacy or health shop? Join the founding network.</p>
            <Button onClick={() => navigate('/register')} className="bg-blue-600 hover:bg-blue-700 rounded-full px-8" data-testid="network-join-btn">
              Join the Network <ArrowRight className="ml-2 w-4 h-4" />
            </Button>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <Badge className="mb-4">Simple Pay-As-You-Earn</Badge>
            <h2 className="font-archivo font-bold text-3xl md:text-4xl text-slate-900 mb-4">
              No monthly fees. Commission-based only.
            </h2>
            <p className="text-slate-600 max-w-2xl mx-auto">
              Sign up for free. You only pay when you earn — a flat 20% commission on each completed trip. A small fee applies if you cancel a trip more than 5 minutes after accepting.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto">
            <Card className="p-8 text-center border-2 border-blue-600 shadow-[0_8px_24px_rgba(37,99,235,0.15)]">
              <div className="w-14 h-14 mx-auto rounded-xl bg-blue-100 flex items-center justify-center mb-4">
                <CreditCard className="w-7 h-7 text-blue-600" />
              </div>
              <p className="text-sm text-slate-500 mb-1">Platform Commission</p>
              <p className="font-archivo font-black text-5xl text-slate-900">20%</p>
              <p className="text-sm text-slate-500 mt-2">of every completed trip</p>
            </Card>
            <Card className="p-8 text-center border border-slate-200">
              <div className="w-14 h-14 mx-auto rounded-xl bg-emerald-100 flex items-center justify-center mb-4">
                <Clock className="w-7 h-7 text-emerald-600" />
              </div>
              <p className="text-sm text-slate-500 mb-1">Free Cancel Window</p>
              <p className="font-archivo font-black text-5xl text-slate-900">5 min</p>
              <p className="text-sm text-slate-500 mt-2">after accepting a trip</p>
            </Card>
            <Card className="p-8 text-center border border-slate-200">
              <div className="w-14 h-14 mx-auto rounded-xl bg-amber-100 flex items-center justify-center mb-4">
                <Shield className="w-7 h-7 text-amber-600" />
              </div>
              <p className="text-sm text-slate-500 mb-1">Late Cancellation Fee</p>
              <p className="font-archivo font-black text-5xl text-slate-900">$15</p>
              <p className="text-sm text-slate-500 mt-2">beyond the grace window</p>
            </Card>
          </div>

          <div className="text-center mt-12">
            <Button
              size="lg"
              onClick={() => navigate('/register')}
              className="bg-blue-600 hover:bg-blue-700 rounded-full text-lg px-8"
              data-testid="pricing-cta-btn"
            >
              Start Earning — Free Signup <ArrowRight className="ml-2 w-5 h-5" />
            </Button>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-6 hero-gradient">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="font-archivo font-bold text-3xl md:text-4xl text-white mb-6">
            Ready to Start Earning?
          </h2>
          <p className="text-slate-300 text-lg mb-8 max-w-2xl mx-auto">
            Complete your driver registration in minutes. Every driver is credential-verified before their first medical delivery.
          </p>
          <Button 
            size="lg"
            onClick={() => navigate('/register')}
            className="bg-white text-slate-900 hover:bg-slate-100 rounded-full text-lg px-8"
            data-testid="cta-register-btn"
          >
            Register Now <ArrowRight className="ml-2 w-5 h-5" />
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 bg-slate-900 text-white">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-5 gap-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                  <Truck className="w-6 h-6 text-white" />
                </div>
                <span className="font-archivo font-bold text-xl">MediTrans</span>
              </div>
              <p className="text-slate-400 text-sm">
                Ontario's trusted medical transportation network.
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Platform</h4>
              <ul className="space-y-2 text-slate-400 text-sm">
                <li><a href="#features" className="hover:text-white transition-colors">How It Works</a></li>
                <li><a href="#pricing" className="hover:text-white transition-colors">Pricing</a></li>
                <li><a href="#permits" className="hover:text-white transition-colors">Requirements</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Resources</h4>
              <ul className="space-y-2 text-slate-400 text-sm">
                <li><a href="https://www.ontario.ca/page/commercial-vehicle-operators-registration-cvor" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">CVOR Info</a></li>
                <li><a href="https://tc.canada.ca/en/dangerous-goods" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">TDG Training</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Legal</h4>
              <ul className="space-y-2 text-slate-400 text-sm">
                <li><a href="/privacy" className="hover:text-white transition-colors" data-testid="footer-privacy-link">Privacy Policy</a></li>
                <li><a href="/terms" className="hover:text-white transition-colors" data-testid="footer-terms-link">Terms of Service</a></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-4">Contact</h4>
              <ul className="space-y-2 text-slate-400 text-sm">
                <li>support@meditrans.ca</li>
                <li>1-800-MEDI-ONT</li>
              </ul>
            </div>
          </div>
          <div className="border-t border-slate-800 mt-8 pt-8 text-center text-slate-400 text-sm">
            © {new Date().getFullYear()} MediTrans Ontario. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
