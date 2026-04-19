import React from 'react';
import { Star } from 'lucide-react';

/**
 * Reusable star rating input/display.
 *
 * Props:
 *  - value: 0-5 (can be fractional for display)
 *  - onChange: (newVal) => void  (omit for read-only)
 *  - size: 'sm' | 'md' | 'lg'
 *  - testidPrefix: string used for data-testid on each star
 */
export default function StarRating({ value = 0, onChange, size = 'md', testidPrefix = 'star' }) {
  const [hover, setHover] = React.useState(0);
  const readOnly = !onChange;
  const current = hover || value;

  const sizeMap = {
    sm: 'w-4 h-4',
    md: 'w-7 h-7',
    lg: 'w-10 h-10'
  };
  const cls = sizeMap[size] || sizeMap.md;

  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map(n => {
        const filled = n <= Math.round(current);
        const Component = readOnly ? 'span' : 'button';
        const extra = readOnly ? {} : {
          type: 'button',
          onMouseEnter: () => setHover(n),
          onMouseLeave: () => setHover(0),
          onClick: () => onChange(n),
          'data-testid': `${testidPrefix}-${n}`
        };
        return (
          <Component
            key={n}
            className={readOnly ? '' : 'transition-transform hover:scale-110 cursor-pointer'}
            {...extra}
          >
            <Star
              className={`${cls} ${filled ? 'text-amber-400 fill-amber-400' : 'text-slate-300'}`}
            />
          </Component>
        );
      })}
    </div>
  );
}
