import React from 'react';
import { Truck, FileText, Scale, Ban, CreditCard, ShieldCheck, AlertTriangle } from 'lucide-react';

const Section = ({ icon: Icon, title, children }) => (
  <section className="mb-8">
    <h2 className="text-lg font-bold text-slate-900 font-archivo flex items-center gap-2 mb-2"><Icon className="w-5 h-5 text-blue-600" />{title}</h2>
    <div className="text-sm text-slate-600 space-y-2">{children}</div>
  </section>
);

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4" data-testid="terms-page">
      <div className="max-w-3xl mx-auto bg-white rounded-2xl shadow-[0_4px_24px_rgba(0,0,0,0.06)] p-8">
        <div className="flex items-center gap-2 mb-6">
          <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center"><Truck className="w-5 h-5 text-white" /></div>
          <span className="font-archivo font-bold text-lg text-slate-900">MediTrans Ontario</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 font-archivo mb-1">Terms of Service</h1>
        <p className="text-xs text-slate-400 mb-8">Version 1.0 · These terms govern use of the MediTrans Ontario platform by drivers, facilities, dispatchers and administrators.</p>

        <Section icon={FileText} title="The service">
          <p>MediTrans Ontario is a logistics marketplace connecting healthcare facilities with independent, credential-verified couriers for the transport of medical and biological products within Ontario, Canada. MediTrans is a technology platform: couriers are independent contractors, not employees, and facilities remain responsible for the lawful packaging and description of the items they ship.</p>
        </Section>
        <Section icon={ShieldCheck} title="Driver obligations">
          <p>Drivers must hold and keep current all required credentials (valid Ontario driver's licence, vehicle insurance, CVOR where applicable, TDG training for dangerous goods, and a vulnerable-sector check). Drivers whose credentials lapse — including expired insurance — are automatically ineligible for new deliveries until compliant. Chain-of-custody steps (pickup confirmation, transit updates, delivery signature) are mandatory for every job.</p>
        </Section>
        <Section icon={CreditCard} title="Fees & payments">
          <p>Facilities are charged per delivery based on distance (or agreed flat/contract terms) plus applicable HST. The platform retains a commission (default 20%) from the driver's gross payout on completed trips. A late-cancellation fee applies when a driver cancels beyond the free-cancellation window after accepting a job. Monthly statements and invoices are available in the Billing section.</p>
        </Section>
        <Section icon={Ban} title="Prohibited use">
          <p>The platform must not be used to transport people, controlled substances outside a lawful supply chain, or any item misdescribed to avoid handling requirements. Accounts may be suspended for credential fraud, custody-record falsification, or abuse of recipients, facilities or drivers.</p>
        </Section>
        <Section icon={AlertTriangle} title="Liability">
          <p>MediTrans provides the platform "as is". To the maximum extent permitted by Ontario law, MediTrans is not liable for indirect or consequential damages arising from delays, spoilage or loss in transit; facilities and drivers must maintain appropriate insurance for the goods they ship and carry.</p>
        </Section>
        <Section icon={Scale} title="Governing law">
          <p>These terms are governed by the laws of the Province of Ontario and the federal laws of Canada. Disputes are subject to the exclusive jurisdiction of the courts of Ontario. Our <a href="/privacy" className="text-blue-600 underline">Privacy Policy</a> forms part of these terms.</p>
        </Section>
        <p className="text-xs text-slate-400 mt-6">Questions: support@meditrans.ca</p>
      </div>
    </div>
  );
}
