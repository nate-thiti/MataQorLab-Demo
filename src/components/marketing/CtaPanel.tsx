// @ts-nocheck
import MarketingButton from './MarketingButton';

const CtaPanel = ({
  title,
  description,
  buttonText,
  buttonTo,
  buttonHref,
  buttonVariant = 'secondary',
  className = '',
}) => {
  return (
    <section className={`py-12 px-6 max-w-5xl mx-auto ${className}`}>
      <div className="marketing-cta-panel p-8 md:p-12 text-center flex flex-col items-center justify-center space-y-6" data-reveal data-spotlight>
        <h2 className="marketing-heading text-2xl md:text-3xl font-bold tracking-tight">
          {title}
        </h2>
        {description && (
          <p className="marketing-subtext text-sm md:text-base max-w-md leading-relaxed">
            {description}
          </p>
        )}
        {buttonText && (buttonTo || buttonHref) && (
          <MarketingButton
            variant={buttonVariant}
            to={buttonTo}
            href={buttonHref}
            className="px-10 py-3.5 text-sm"
          >
            {buttonText}
          </MarketingButton>
        )}
      </div>
    </section>
  );
};

export default CtaPanel;
