import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { 
  Truck, Shield, FileText, MapPin, CreditCard, 
  CheckCircle, ArrowRight, Clock, Thermometer
} from 'lucide-react';

const LandingPage = () => {
  const navigate = useNavigate();

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
              <Badge variant="outline" className="ml-2 text-red-600 border-red-200 bg-red-50">Ontario</Badge>
            </div>
            <div className="hidden md:flex items-center gap-6">
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
              <Badge className="bg-blue-500/20 text-blue-200 border-blue-400/30 mb-6">
                Ontario's Medical Transport Network
              </Badge>
              <h1 className="font-archivo font-black text-4xl sm:text-5xl lg:text-6xl leading-tight mb-6">
                Deliver Critical Medical Supplies Across Ontario
              </h1>
              <p className="text-lg text-slate-300 mb-8 max-w-xl">
                Join the trusted network of certified drivers transporting biological samples, 
                pharmaceuticals, and medical equipment throughout the Greater Toronto Area and beyond.
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
                  onClick={() => navigate('/register')}
                  className="border-slate-400 text-white hover:bg-white/10 rounded-full text-lg px-8"
                  data-testid="hero-book-transport-btn"
                >
                  Book Transport
                </Button>
              </div>
            </div>
            <div className="relative animate-fade-in-up stagger-2">
              <img 
                src="https://images.unsplash.com/photo-1646920912229-bc0d5d94e68b?crop=entropy&cs=srgb&fm=jpg&q=85&w=600" 
                alt="Medical courier ready for delivery"
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
                src="https://images.unsplash.com/photo-1628182087681-b6e7d4a26efd?crop=entropy&cs=srgb&fm=jpg&q=85&w=600"
                alt="Toronto skyline representing Ontario coverage"
                className="rounded-2xl shadow-xl"
              />
            </div>
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
            Join hundreds of drivers already delivering medical supplies across Ontario. 
            Complete your registration in minutes.
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
          <div className="grid md:grid-cols-4 gap-8">
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
              <h4 className="font-semibold mb-4">Contact</h4>
              <ul className="space-y-2 text-slate-400 text-sm">
                <li>support@meditrans.ca</li>
                <li>1-800-MEDI-ONT</li>
              </ul>
            </div>
          </div>
          <div className="border-t border-slate-800 mt-8 pt-8 text-center text-slate-400 text-sm">
            © 2024 MediTrans Ontario. All rights reserved.
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
